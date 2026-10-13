"""Dictionary- and rule-based NER for primary cells, immune cell subsets, and extracellular vesicles.

PubTator3's "CellLine" category only indexes in vitro cultured cell lines (e.g. HeLa, Huh-7,
HepG2 from Cellosaurus). It has no concept of primary cell types, stem cells, tumor-microenvironment
stromal cells, or immune cell subsets -- leaving critical entities like "mesenchymal stem cells"
(MSCs), "tumor-associated macrophages" (TAMs), "regulatory T cells" (Tregs), "cancer-associated
fibroblasts" (CAFs), or "exosomes / extracellular vesicles" completely unannotated.

This module closes that gap:
1. Grounded in Cell Ontology (CL) IDs where applicable, or standard EV/nanocarrier IDs.
2. Case-aware abbreviation matching: multi-word phrases ("tumor-associated macrophages") match
   case-insensitively, while short abbreviations ("TAM", "Treg", "CAF", "MDSC", "EV") require
   appropriate casing to prevent matching ordinary English words.
3. Assigns entity type "CellLine", mirroring PubTator's cellular classification and seamlessly
   inheriting Cytoscape node coloring (#BDBDBD) and downstream relations.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from netmedex.pubtator_data import PubTatorAnnotation

# Curated catalog of primary cells, immune subsets, stem cells, and extracellular vesicles:
# Format: (canonical_name, ontology_id, set_of_synonyms)
_CELL_TYPE_CATALOG: list[tuple[str, str, list[str]]] = [
    # --- Stem Cells ---
    (
        "Mesenchymal stem cell",
        "CL:0000134",
        [
            "mesenchymal stem cells", "mesenchymal stem cell",
            "mesenchymal stromal cells", "mesenchymal stromal cell",
            "bone marrow mesenchymal stem cells", "BMSCs", "BMSC",
            "adipose-derived stem cells", "ADSCs", "ADSC", "MSCs", "MSC",
        ],
    ),
    (
        "Cancer stem cell",
        "CL:0001064",
        [
            "cancer stem cells", "cancer stem cell",
            "tumor stem cells", "tumor stem cell",
            "CSCs", "CSC",
        ],
    ),
    (
        "Hematopoietic stem cell",
        "CL:0000037",
        [
            "hematopoietic stem cells", "hematopoietic stem cell",
            "HSCs", "HSC",
        ],
    ),
    (
        "Induced pluripotent stem cell",
        "CL:0002248",
        [
            "induced pluripotent stem cells", "induced pluripotent stem cell",
            "iPSCs", "iPSC",
        ],
    ),

    # --- Immune Cell Subsets ---
    (
        "Regulatory T cell",
        "CL:0000815",
        [
            "regulatory T cells", "regulatory T cell",
            "regulatory T lymphocytes", "regulatory T lymphocyte",
            "Tregs", "Treg", "Treg cells", "Treg cell",
        ],
    ),
    (
        "CD8-positive T cell",
        "CL:0000794",
        [
            "CD8+ T cells", "CD8+ T cell", "CD8(+) T cells", "CD8(+) T cell",
            "CD8+ T lymphocytes", "cytotoxic T cells", "cytotoxic T cell",
            "cytotoxic T lymphocytes", "CTLs", "CTL",
        ],
    ),
    (
        "CD4-positive T cell",
        "CL:0000492",
        [
            "CD4+ T cells", "CD4+ T cell", "CD4(+) T cells", "CD4(+) T cell",
            "CD4+ T lymphocytes", "T helper cells", "T helper cell",
            "Th cells", "Th cell",
        ],
    ),
    (
        "Tumor-associated macrophage",
        "CL:0001072",
        [
            "tumor-associated macrophages", "tumor-associated macrophage",
            "tumour-associated macrophages", "tumour-associated macrophage",
            "TAMs", "TAM",
        ],
    ),
    (
        "Kupffer cell",
        "CL:0000091",
        [
            "Kupffer cells", "Kupffer cell",
        ],
    ),
    (
        "M1 macrophage",
        "CL:0001083",
        [
            "M1 macrophages", "M1 macrophage",
            "M1-polarized macrophages", "M1-like macrophages",
        ],
    ),
    (
        "M2 macrophage",
        "CL:0001084",
        [
            "M2 macrophages", "M2 macrophage",
            "M2-polarized macrophages", "M2-like macrophages",
        ],
    ),
    (
        "Myeloid-derived suppressor cell",
        "CL:0000977",
        [
            "myeloid-derived suppressor cells", "myeloid-derived suppressor cell",
            "MDSCs", "MDSC",
        ],
    ),
    (
        "Dendritic cell",
        "CL:0000451",
        [
            "dendritic cells", "dendritic cell",
            "DCs", "DC",
        ],
    ),
    (
        "Natural killer cell",
        "CL:0000623",
        [
            "natural killer cells", "natural killer cell",
            "NK cells", "NK cell",
        ],
    ),
    (
        "Neutrophil",
        "CL:0000775",
        [
            "neutrophils", "neutrophil",
            "tumor-associated neutrophils", "TANs",
        ],
    ),
    (
        "Monocyte",
        "CL:0000576",
        [
            "monocytes", "monocyte",
        ],
    ),
    (
        "Macrophage",
        "CL:0000235",
        [
            "macrophages", "macrophage",
        ],
    ),
    (
        "T cell",
        "CL:0000084",
        [
            "T cells", "T cell", "T lymphocytes", "T lymphocyte",
        ],
    ),
    (
        "B cell",
        "CL:0000236",
        [
            "B cells", "B cell", "B lymphocytes", "B lymphocyte",
        ],
    ),

    # --- Stromal & Parenchymal Cells ---
    (
        "Cancer-associated fibroblast",
        "CL:0001073",
        [
            "cancer-associated fibroblasts", "cancer-associated fibroblast",
            "carcinoma-associated fibroblasts", "CAFs", "CAF",
        ],
    ),
    (
        "Hepatic stellate cell",
        "CL:0000632",
        [
            "hepatic stellate cells", "hepatic stellate cell",
        ],
    ),
    (
        "Endothelial cell",
        "CL:0000115",
        [
            "endothelial cells", "endothelial cell",
            "vascular endothelial cells", "vascular endothelial cell",
        ],
    ),
    (
        "Hepatocyte",
        "CL:0000182",
        [
            "hepatocytes", "hepatocyte",
            "primary hepatocytes", "primary human hepatocytes",
        ],
    ),

    # --- Extracellular Vesicles & Delivery Vehicles ---
    (
        "Exosome",
        "EV:0000001",
        [
            "exosomes", "exosome",
            "exosomal",
        ],
    ),
    (
        "Extracellular vesicle",
        "EV:0000002",
        [
            "extracellular vesicles", "extracellular vesicle",
            "small extracellular vesicles", "sEVs", "sEV",
            "EVs", "EV",
        ],
    ),
    (
        "Microvesicle",
        "EV:0000003",
        [
            "microvesicles", "microvesicle",
            "ectosomes", "ectosome",
        ],
    ),
    (
        "Lipid nanoparticle",
        "DDS:0000001",
        [
            "lipid nanoparticles", "lipid nanoparticle",
            "LNPs", "LNP",
        ],
    ),
]


class _CellTypeMatcher:
    def __init__(self, catalog: list[tuple[str, str, list[str]]]):
        self.rules: list[tuple[str, str, re.Pattern]] = []
        for canonical_name, ontology_id, synonyms in catalog:
            # Sort synonyms by length descending so longer phrases match first
            sorted_syns = sorted(synonyms, key=len, reverse=True)
            alternatives = []
            for s in sorted_syns:
                # If synonym contains an uppercase letter and is short (<= 5 chars), match case-sensitively
                # as an abbreviation (e.g. "TAM", "Treg", "CAF", "MDSC", "EV").
                # Otherwise match case-insensitively.
                if any(c.isupper() for c in s) and len(s) <= 5:
                    alternatives.append(re.escape(s))
                else:
                    alternatives.append(f"(?i:{re.escape(s)})")
            pattern = re.compile(rf"(?<![A-Za-z0-9_-])(?:{'|'.join(alternatives)})(?![A-Za-z0-9_-])")
            self.rules.append((canonical_name, ontology_id, pattern))

    def scan(self, text: str) -> list[tuple[int, int, str, str, str]]:
        """Returns list of (start, end, raw_text, canonical_name, ontology_id)."""
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


_MATCHER = _CellTypeMatcher(_CELL_TYPE_CATALOG)


def find_cell_type_annotations(
    pmid: str,
    title: str,
    abstract: str | None,
    existing_annotations: Sequence[PubTatorAnnotation] | None = None,
) -> list[PubTatorAnnotation]:
    """Scan title + abstract for primary cell types, immune subsets, and extracellular vesicles.

    Returns synthetic PubTatorAnnotation objects (type "CellLine") that can be fed
    straight into PubTatorNodeCollection.add_node() alongside the article's real
    PubTator annotations.
    """
    text = f"{title} {abstract or ''}"
    if not text.strip():
        return []

    # Map existing exact spans to skip duplicates if already annotated
    existing_spans = set()
    if existing_annotations:
        for a in existing_annotations:
            if a.type == "CellLine" and str(a.mesh or "-") not in ("-", ""):
                existing_spans.add((a.start, a.end))

    hits = _MATCHER.scan(text)
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
                type="CellLine",
                mesh=ontology_id,
            )
        )
    return annotations
