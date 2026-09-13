"""Deterministic audit checks for graph-derived claims and their supporting hops."""

from __future__ import annotations

import re
from typing import Any

from netmedex.relation_types import normalize_relation_type


RELATION_CUES = {
    "activates": {"activate", "activates", "activated", "activation", "increase", "increased"},
    "upregulates": {
        "upregulate",
        "upregulates",
        "upregulated",
        "upregulation",
        "increase",
        "increased",
    },
    "inhibits": {"inhibit", "inhibits", "inhibited", "inhibition", "reduce", "reduced"},
    "downregulates": {
        "downregulate",
        "downregulates",
        "downregulated",
        "downregulation",
        "decrease",
        "decreased",
        "reduce",
        "reduced",
        "negatively regulate",
        "negatively regulates",
        "negatively regulated",
        "negatively regulating",
        "negative regulation",
    },
    "targets": {"target", "targets", "targeted", "targeting", "direct target"},
    "suppresses": {"suppress", "suppresses", "suppressed", "reduce", "reduced"},
    "associated_with": {
        "associate",
        "associated",
        "association",
        "linked",
        "correlate",
        "patients with",
        "influence",
        "influences",
        "relationship",
    },
    "co_occurs_with": {"co occur", "co occurs", "co occurred", "co mention"},
    "regulates": {"regulate", "regulates", "regulated", "regulation"},
    "treats": {"treat", "treats", "treated", "treatment", "ameliorate", "ameliorated"},
    "ameliorates": {
        "ameliorate",
        "ameliorates",
        "ameliorated",
        "alleviate",
        "alleviates",
        "alleviated",
        "improve",
        "improves",
        "improved",
        "protect",
        "protects",
        "protected",
    },
    "prevents": {"prevent", "prevents", "prevented", "prevention"},
    "causes": {
        "cause",
        "causes",
        "caused",
        "causal",
        "drive",
        "drives",
        "driver",
        "driven",
        "lead to",
        "leads to",
        "led to",
        "result in",
        "results in",
        "induce",
        "induces",
        "induced",
        "sufficient to",
    },
    "promotes": {
        "promote",
        "promotes",
        "promoted",
        "promotion",
        "inflammatory cascade",
        "carcinogenic mechanism",
    },
    "leads_to": {
        "lead to",
        "leads to",
        "led to",
        "progression to",
        "progresses to",
        "culminating in",
    },
}


def _normalized_text(value: Any) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", str(value).casefold()).split())


def _relation_cues(relation: str) -> set[str]:
    normalized = normalize_relation_type(relation)
    cues = set(RELATION_CUES.get(normalized, set()))
    cues.add(normalized.replace("_", " "))
    if normalized.endswith("s"):
        cues.add(normalized[:-1].replace("_", " "))
    return {_normalized_text(cue) for cue in cues if cue}


def _contains_relation(text: str, relation: str) -> bool:
    normalized = _normalized_text(text)
    return any(cue and cue in normalized for cue in _relation_cues(relation))


def relation_supported_by_text(text: str, relation: str) -> bool:
    """Public high-precision relation/quote consistency check for graph gating."""
    return _contains_relation(text, relation)


def _extract_pmids(text: str) -> set[str]:
    # Biomedical PMIDs are long enough to distinguish them from years and hop numbers.
    return set(re.findall(r"\b\d{6,9}\b", text))


def _entity_position(text: str, aliases: list[str]) -> int | None:
    positions = [
        text.find(alias)
        for alias in (_normalized_text(value) for value in aliases)
        if alias and alias in text
    ]
    return min(positions) if positions else None


def _path_lookup(paths: list[dict]) -> dict[str, dict]:
    lookup = {}
    for path in paths:
        for key in ("path_signature", "path_id"):
            value = path.get(key)
            if value:
                lookup[str(value).casefold()] = path
    return lookup


def verify_claim_to_path(
    claim_text: str,
    path_reference: str,
    paths: list[dict],
    *,
    claim_id: str = "HC-01",
) -> dict:
    """Verify one atomic claim against one explicit, claim-safe graph path."""
    path = _path_lookup(paths).get(str(path_reference).casefold())
    if path is None:
        return {
            "claim_id": claim_id,
            "path_id": path_reference,
            "verdict": "unsupported",
            "reasons": ["path_not_found"],
        }

    reasons = []
    if not path.get("claim_safe", False) or path.get("gate_tier") != "A":
        reasons.append("path_not_tier_a_claim_safe")

    names = [str(name) for name in path.get("names", [])]
    node_aliases = path.get("node_aliases", [])
    relations = [str(relation) for relation in path.get("relations", [])]
    pmid_groups = path.get("edge_pmids", [])
    quote_groups = path.get("edge_evidence_quotes", [])
    cited_pmids = _extract_pmids(claim_text)

    for index in range(max(0, len(names) - 1)):
        hop_number = index + 1
        # Canonical renderers label every hop.  When labels are present, audit the
        # corresponding clause rather than the entire line; this handles repeated
        # bridge names and cycles without mistaking an earlier occurrence for direction.
        hop_match = re.search(
            rf"\bHOP\s+{hop_number}\s*:\s*(.*?)(?=\s*;\s*HOP\s+\d+\s*:|$)",
            claim_text,
            flags=re.IGNORECASE,
        )
        hop_text = hop_match.group(1) if hop_match else claim_text
        normalized_hop = _normalized_text(hop_text)
        source_aliases = [names[index]]
        target_aliases = [names[index + 1]]
        if index < len(node_aliases):
            source_aliases.extend(str(alias) for alias in node_aliases[index])
        if index + 1 < len(node_aliases):
            target_aliases.extend(str(alias) for alias in node_aliases[index + 1])
        source_position = _entity_position(normalized_hop, source_aliases)
        target_position = _entity_position(normalized_hop, target_aliases)
        relation = relations[index] if index < len(relations) else "associated_with"
        if source_position is None:
            reasons.append(f"hop_{hop_number}_source_missing")
        if target_position is None:
            reasons.append(f"hop_{hop_number}_target_missing")
        if (
            source_position is not None
            and target_position is not None
            and source_position > target_position
        ):
            reasons.append(f"hop_{hop_number}_direction_mismatch")
        if not _contains_relation(hop_text, relation):
            reasons.append(f"hop_{hop_number}_relation_mismatch")

        hop_pmids = {
            str(pmid) for pmid in (pmid_groups[index] if index < len(pmid_groups) else [])
        }
        hop_cited_pmids = _extract_pmids(hop_text) if hop_match else cited_pmids
        if not hop_pmids or not (hop_pmids & hop_cited_pmids):
            reasons.append(f"hop_{hop_number}_pmid_missing")

        quotes = quote_groups[index] if index < len(quote_groups) else []
        if not quotes:
            reasons.append(f"hop_{hop_number}_quote_missing")
        elif not any(_contains_relation(str(quote), relation) for quote in quotes):
            reasons.append(f"hop_{hop_number}_quote_relation_mismatch")

    return {
        "claim_id": claim_id,
        "path_id": path_reference,
        "verdict": "supported" if not reasons else "unsupported",
        "reasons": reasons,
    }


def verify_answer_graph_claims(answer: str, paths: list[dict]) -> dict:
    """Find PATH-cited lines in an answer and audit each as one atomic claim."""
    claim_lines = []
    # A path identifier always contains at least one digit (hex signatures and IDs such
    # as TH001-P01 both do).  Requiring a digit prevents ordinary prose such as
    # "Path: dysbiosis to bone loss" from being misclassified as an explicit ID claim.
    path_pattern = re.compile(
        r"\bPATH\b\s*[:#]?\s*((?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{6,})",
        re.IGNORECASE,
    )
    for line in str(answer or "").splitlines():
        for match in path_pattern.finditer(line):
            claim_lines.append((line.strip(), match.group(1)))

    claims = [
        verify_claim_to_path(text, reference, paths, claim_id=f"HC-{index:02d}")
        for index, (text, reference) in enumerate(claim_lines, start=1)
    ]
    return {
        "mode": "deterministic_audit_only",
        "path_cited_claim_count": len(claims),
        "supported_claim_count": sum(claim["verdict"] == "supported" for claim in claims),
        "unsupported_claim_count": sum(claim["verdict"] == "unsupported" for claim in claims),
        "no_path_citations_detected": not claims,
        "claims": claims,
    }
