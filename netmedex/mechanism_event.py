"""Evidence-grounded mechanism events represented on semantic graph edges.

A mechanism is not treated as a free-text NER node. It is a reified assertion
whose identity depends on canonical endpoints, direction, PMID, relation and
supporting quote. This preserves provenance without polluting the entity graph.
"""

from __future__ import annotations

from typing import Any

from netmedex.claim_verifier import relation_supported_by_text
from netmedex.relation_types import is_directional_relation, normalize_relation_type
from netmedex.utils import generate_stable_id

MECHANISM_EVENT_SCHEMA_VERSION = 1


def build_mechanism_event(
    *,
    source_id: str | None,
    target_id: str | None,
    pmid: str | None,
    relation: str | None,
    evidence: str | None,
    confidence: float | None,
    study_type: str | None = None,
) -> dict[str, Any] | None:
    """Return an event only when a directional assertion has aligned evidence."""
    source = str(source_id or "").strip()
    target = str(target_id or "").strip()
    citation = str(pmid or "").strip()
    canonical_relation = normalize_relation_type(str(relation or "").strip())
    quote = " ".join(str(evidence or "").split())
    if not source or not target or not citation or not quote:
        return None
    if not is_directional_relation(canonical_relation):
        return None
    if not relation_supported_by_text(quote, canonical_relation):
        return None
    event_key = "|".join(
        (citation, source, canonical_relation, target, quote.casefold())
    )
    return {
        "event_id": generate_stable_id(f"mechanism_event|{event_key}"),
        "schema_version": MECHANISM_EVENT_SCHEMA_VERSION,
        "pmid": citation,
        "source_id": source,
        "target_id": target,
        "relation": canonical_relation,
        "evidence": quote,
        "confidence": float(confidence) if confidence is not None else None,
        "study_type": study_type,
        "grounding_status": "directional_quote_aligned",
    }
