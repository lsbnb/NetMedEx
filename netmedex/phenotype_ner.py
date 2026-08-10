"""Dictionary-based NER for biological process (GO) and phenotype (HPO) mentions.

PubTator3's own NER only covers Gene, Chemical, Disease, CellLine, Species, and Variant --
it has no biological-process or phenotype category at all, so terms like "osteoblast
differentiation" or "angiogenesis" never become graph nodes no matter how well a downstream
LLM extracts relations mentioning them. This module closes that gap with a deterministic,
LLM-free dictionary lookup against GO's biological_process branch and HPO, mirroring how
Disease nodes already get a canonical MeSH ID: matches here get a canonical GO:/HP: ID, so
they dedupe and merge exactly like any other PubTator-derived node.

Precision/recall tradeoff: this is a fixed-vocabulary lookup, not a trained NER model. It will
miss paraphrases not in GO/HPO's own name+synonym list (e.g. a novel or colloquial phrasing),
but every match it does produce is grounded in a real ontology ID -- see
scripts/build_phenotype_terms.py for exactly which synonym classes are included.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from netmedex.pubtator_data import PubTatorAnnotation

_DATA_PATH = Path(__file__).parent / "data" / "phenotype_terms.json"
_MAX_NGRAM = 8
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")


@lru_cache(maxsize=1)
def _load_term_index() -> dict[str, tuple[str, str, str]]:
    if not _DATA_PATH.exists():
        return {}
    with _DATA_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {k: tuple(v) for k, v in raw.items()}


def find_phenotype_annotations(pmid: str, title: str, abstract: str | None) -> list[PubTatorAnnotation]:
    """Scan title+abstract for GO biological_process / HPO phenotype term mentions.

    Returns synthetic PubTatorAnnotation objects (type "BiologicalProcess" or "Phenotype",
    mesh=the GO:/HP: ID) that can be fed straight into PubTatorNodeCollection.add_node()
    alongside the article's real PubTator annotations.

    Matching is greedy, longest-span-first, non-overlapping: once a span matches, scanning
    resumes after it rather than also checking shorter sub-spans starting within it.
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
