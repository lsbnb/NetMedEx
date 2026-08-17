#!/usr/bin/env python3
"""Audit how many additional claim-safe paths already exist without relaxing gates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def tier_a_claim_safe(path: dict) -> bool:
    supports = path.get("edge_supports") or []
    return (
        path.get("gate_tier") == "A"
        and path.get("claim_safe") is True
        and bool(supports)
        and all(
            edge.get("support_tier") == "A"
            and float(edge.get("selected_confidence") or 0) >= 0.8
            and edge.get("selected_quote")
            and edge.get("quote_relation_aligned")
            for edge in supports
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with (args.benchmark_dir / "candidate_audit.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))

    audit = []
    for row in rows:
        result = json.loads(Path(row["source_result"]).read_text(encoding="utf-8"))
        selected = next(
            path for path in result["graph"]["paths"]
            if path.get("path_signature") == row["path_signature"]
        )
        selected_names = selected.get("names") or []
        start, end = selected_names[0].casefold(), selected_names[-1].casefold()
        unique = {}
        for path in result["graph"]["paths"]:
            names = path.get("names") or []
            endpoint_match = (
                len(names) >= 2
                and names[0].casefold() == start
                and names[-1].casefold() == end
            )
            if tier_a_claim_safe(path) and endpoint_match:
                unique[path["path_signature"]] = path
        audit.append(
            {
                "question_id": row["question_id"],
                "frozen_path_count": 1,
                "available_unique_claim_safe_endpoint_matched_paths": len(unique),
                "additional_available": max(0, len(unique) - 1),
                "path_signatures": sorted(unique),
            }
        )
    available = sum(row["available_unique_claim_safe_endpoint_matched_paths"] for row in audit)
    payload = {
        "gate_unchanged": True,
        "gate": "path Tier A + claim_safe + every edge quote-aligned and confidence >= 0.8",
        "endpoint_rule": "case-insensitive exact start/end node-name match",
        "frozen_paths": len(audit),
        "available_paths": available,
        "additional_paths": available - len(audit),
        "relative_increase_percent": round((available / len(audit) - 1) * 100, 1),
        "questions_with_more_than_one_path": sum(
            row["available_unique_claim_safe_endpoint_matched_paths"] > 1 for row in audit
        ),
        "items": audit,
        "caution": "Availability does not imply that all paths should be placed in answer context.",
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
