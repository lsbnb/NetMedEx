#!/usr/bin/env python3
"""Aggregate hidden-claim judges by per-field majority and report preregistered endpoints."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

try:
    from evaluation.metrics import krippendorff_alpha
except ModuleNotFoundError:  # Direct execution: python evaluation/summarize_hidden_claim_panel.py
    from metrics import krippendorff_alpha


BINARY_FIELDS = [
    "hybrid_only",
    "path_traceable",
    "evidence_support",
    "relation_direction_correct",
    "multi_document_or_hop",
    "unsupported_novelty",
]
ORDINAL_FIELDS = ["non_obviousness", "research_utility"]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("rater_id", "").strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, action="append", required=True)
    parser.add_argument("--question-count", type=int, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in args.ratings:
        for row in read_rows(path):
            by_item[row["hidden_claim_id"]].append(row)

    consensus_rows = []
    for item_id, ratings in sorted(by_item.items()):
        consensus: dict[str, object] = {"hidden_claim_id": item_id}
        for field in BINARY_FIELDS:
            values = [int(row[field]) for row in ratings]
            consensus[field] = int(sum(values) > len(values) / 2)
        for field in ORDINAL_FIELDS:
            consensus[field] = median(int(row[field]) for row in ratings)
        consensus["rater_count"] = len(ratings)
        consensus["validated_hidden_claim"] = int(
            consensus["hybrid_only"] == 1
            and consensus["path_traceable"] == 1
            and consensus["evidence_support"] == 1
            and consensus["relation_direction_correct"] == 1
            and consensus["multi_document_or_hop"] == 1
            and consensus["non_obviousness"] >= 4
            and consensus["research_utility"] >= 4
            and consensus["unsupported_novelty"] == 0
        )
        consensus_rows.append(consensus)

    reliability = {}
    for field in BINARY_FIELDS:
        reliability[field] = krippendorff_alpha(
            [[int(row[field]) for row in ratings] for ratings in by_item.values()],
            level="nominal",
        )
    for field in ORDINAL_FIELDS:
        reliability[field] = krippendorff_alpha(
            [[int(row[field]) for row in ratings] for ratings in by_item.values()],
            level="ordinal",
        )

    validated = [row for row in consensus_rows if row["validated_hidden_claim"]]
    questions_with_valid = {str(row["hidden_claim_id"]).split("-")[0] for row in validated}
    summary = {
        "human_expert_review_claimed": False,
        "candidate_claims": len(consensus_rows),
        "questions_total": args.question_count,
        "questions_with_traceable_candidates": len(
            {str(row["hidden_claim_id"]).split("-")[0] for row in consensus_rows}
        ),
        "validated_hidden_claims": len(validated),
        "validated_hidden_claims_per_question": len(validated) / args.question_count,
        "questions_with_at_least_one_validated_hidden_claim_fraction": (
            len(questions_with_valid) / args.question_count
        ),
        "validated_hidden_claim_precision": (
            len(validated) / len(consensus_rows) if consensus_rows else 0.0
        ),
        "unsupported_novelty_consensus_rate": (
            sum(int(row["unsupported_novelty"]) for row in consensus_rows)
            / len(consensus_rows)
            if consensus_rows
            else 0.0
        ),
        "field_consensus_positive_rates": {
            field: sum(int(row[field]) for row in consensus_rows) / len(consensus_rows)
            for field in BINARY_FIELDS
        },
        "krippendorff_alpha": reliability,
        "primary_hypothesis_supported": False if not validated else None,
        "note": (
            "With zero validated Hybrid-only claims, the preregistered positive difference "
            "cannot be met even without estimating Text-only hidden claims."
        ),
    }

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(consensus_rows[0]))
        writer.writeheader()
        writer.writerows(consensus_rows)
    args.output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
