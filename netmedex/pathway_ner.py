"""Dictionary-based NER for named signaling/metabolic pathways (KEGG + Reactome).

A named pathway (e.g. "PI3K/AKT pathway", "Wnt signaling pathway") is a distinct entity category
from a biological-process outcome (netmedex/phenotype_ner.py) or an individual gene: a paper often
invokes the pathway directly ("activates the PI3K/AKT pathway") without naming every gene in it,
and PubTator3 has no pathway annotation type at all. This module closes that gap the same way
phenotype_ner.py does -- deterministic, LLM-free dictionary lookup against KEGG's reference
pathway list and Reactome's human pathway list, each match grounded in a real canonical ID
(KEGG map ID or Reactome stable ID) so it dedupes and merges like any other PubTator-derived node.

See scripts/build_pathway_terms.py for exactly how the bundled dictionary is built.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from netmedex.pubtator_data import PubTatorAnnotation

_DATA_PATH = Path(__file__).parent / "data" / "pathway_terms.json"
_MAX_NGRAM = 8
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-'/][A-Za-z0-9]+)*")


@lru_cache(maxsize=1)
def _load_term_index() -> dict[str, tuple[str, str, str]]:
    if not _DATA_PATH.exists():
        return {}
    with _DATA_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {k: tuple(v) for k, v in raw.items()}


def find_pathway_annotations(pmid: str, title: str, abstract: str | None) -> list[PubTatorAnnotation]:
    """Scan title+abstract for named-pathway mentions (KEGG/Reactome).

    Returns synthetic PubTatorAnnotation objects (type "Pathway", mesh=the KEGG/Reactome ID) that
    can be fed straight into PubTatorNodeCollection.add_node() alongside the article's real
    PubTator annotations and any phenotype_ner matches.

    Matching is greedy, longest-span-first, non-overlapping, identical in approach to
    phenotype_ner.find_phenotype_annotations. The token pattern additionally allows "/" within a
    token (unlike phenotype_ner) so that compound names like "PI3K/AKT" are scanned as one token
    rather than being split at the slash.
    """
    index = _load_term_index()
    if not index:
        return []

    text = f"{title} {abstract or ''}"
    tokens = list(_TOKEN_RE.finditer(text))
    if not tokens:
        return []

    annotations: list[PubTatorAnnotation] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        max_span = min(_MAX_NGRAM, n - i)
        for span in range(max_span, 0, -1):
            first, last = tokens[i], tokens[i + span - 1]
            candidate = text[first.start() : last.end()]
            key = candidate.lower()
            hit = index.get(key)
            if hit:
                ontology_id, canonical_name, entity_type = hit
                annotations.append(
                    PubTatorAnnotation(
                        pmid=pmid,
                        start=first.start(),
                        end=last.end(),
                        name=candidate,
                        identifier_name=canonical_name,
                        type=entity_type,
                        mesh=ontology_id,
                    )
                )
                i += span
                matched = True
                break
        if not matched:
            i += 1

    return annotations
