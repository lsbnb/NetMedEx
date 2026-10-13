"""Dictionary-based NER for cellular organelles and subcellular components (GO Cellular Component).

PubTator3 has no cellular component annotation type, and NetMedEx's phenotype_ner.py only covers
GO's biological_process branch and HPO phenotypes. Subcellular structures like "mitochondria",
"endoplasmic reticulum", "lysosomes", and "autophagosomes" are central to mechanism papers
(mitophagy, ER stress, lysosomal degradation) but are otherwise lost or ungrounded.

This module closes that gap:
1. Grounded in canonical Gene Ontology Cellular Component (GO-CC) IDs (e.g. GO:0005739 for mitochondrion).
2. Deterministic, dictionary-based matching with singular/plural and canonical synonyms.
3. Assigns entity type "CellularComponent".
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from netmedex.pubtator_data import PubTatorAnnotation

_ORGANELLE_CATALOG: list[tuple[str, str, list[str]]] = [
    (
        "Mitochondrion",
        "GO:0005739",
        [
            "mitochondria", "mitochondrion",
            "mitochondrial matrix", "mitochondrial membrane",
            "outer mitochondrial membrane", "inner mitochondrial membrane",
        ],
    ),
    (
        "Endoplasmic reticulum",
        "GO:0005783",
        [
            "endoplasmic reticulum", "sarcoplasmic reticulum",
            "rough endoplasmic reticulum", "smooth endoplasmic reticulum",
            "ER lumen", "ER membrane",
        ],
    ),
    (
        "Lysosome",
        "GO:0005764",
        [
            "lysosomes", "lysosome",
            "lysosomal membrane", "lysosomal lumen",
        ],
    ),
    (
        "Golgi apparatus",
        "GO:0005794",
        [
            "Golgi apparatus", "Golgi complex", "Golgi body",
            "trans-Golgi network", "cis-Golgi network",
        ],
    ),
    (
        "Cell nucleus",
        "GO:0005634",
        [
            "nucleus", "nuclei",
            "nuclear envelope", "nuclear membrane", "nucleoplasm",
        ],
    ),
    (
        "Nucleolus",
        "GO:0005730",
        [
            "nucleolus", "nucleoli",
        ],
    ),
    (
        "Peroxisome",
        "GO:0005777",
        [
            "peroxisomes", "peroxisome",
        ],
    ),
    (
        "Autophagosome",
        "GO:0005776",
        [
            "autophagosomes", "autophagosome",
        ],
    ),
    (
        "Endosome",
        "GO:0005768",
        [
            "endosomes", "endosome",
            "early endosomes", "late endosomes", "recycling endosomes",
        ],
    ),
    (
        "Ribosome",
        "GO:0005840",
        [
            "ribosomes", "ribosome",
        ],
    ),
    (
        "Cytosol",
        "GO:0005829",
        [
            "cytosol", "cytoplasm",
        ],
    ),
    (
        "Centrosome",
        "GO:0005813",
        [
            "centrosomes", "centrosome",
        ],
    ),
    (
        "Plasma membrane",
        "GO:0005886",
        [
            "plasma membrane", "cell membrane",
        ],
    ),
]


class _OrganelleMatcher:
    def __init__(self, catalog: list[tuple[str, str, list[str]]]):
        self.rules: list[tuple[str, str, re.Pattern]] = []
        for canonical_name, ontology_id, synonyms in catalog:
            sorted_syns = sorted(synonyms, key=len, reverse=True)
            alternatives = [f"(?i:{re.escape(s)})" for s in sorted_syns]
            pattern = re.compile(rf"(?<![A-Za-z0-9_-])(?:{'|'.join(alternatives)})(?![A-Za-z0-9_-])")
            self.rules.append((canonical_name, ontology_id, pattern))

    def scan(self, text: str) -> list[tuple[int, int, str, str, str]]:
        matches = []
        taken_spans: list[tuple[int, int]] = []
        for canonical_name, ontology_id, pattern in self.rules:
            for m in pattern.finditer(text):
                start, end = m.start(), m.end()
                if any(start < e and s < end for s, e in taken_spans):
                    continue
                raw_text = m.group(0)
                matches.append((start, end, raw_text, canonical_name, ontology_id))
                taken_spans.append((start, end))
        matches.sort(key=lambda x: x[0])
        return matches


_ORGANELLE_MATCHER = _OrganelleMatcher(_ORGANELLE_CATALOG)


def find_organelle_annotations(
    pmid: str,
    title: str,
    abstract: str | None,
    existing_annotations: Sequence[PubTatorAnnotation] | None = None,
) -> list[PubTatorAnnotation]:
    """Scan title + abstract for cellular organelles and subcellular components.

    Returns synthetic PubTatorAnnotation objects (type "CellularComponent", mesh=the GO-CC ID)
    that can be fed straight into PubTatorNodeCollection.add_node() alongside the article's real
    PubTator annotations.
    """
    text = f"{title} {abstract or ''}"
    if not text.strip():
        return []

    existing_spans = set()
    if existing_annotations:
        for a in existing_annotations:
            if a.type == "CellularComponent" and str(a.mesh or "-") not in ("-", ""):
                existing_spans.add((a.start, a.end))

    hits = _ORGANELLE_MATCHER.scan(text)
    annotations: list[PubTatorAnnotation] = []
    for start, end, raw_text, canonical_name, ontology_id in hits:
        if (start, end) in existing_spans:
            continue
        annotations.append(
            PubTatorAnnotation(
                pmid=pmid,
                start=start,
                end=end,
                name=raw_text,
                identifier_name=canonical_name,
                type="CellularComponent",
                mesh=ontology_id,
            )
        )
    return annotations
