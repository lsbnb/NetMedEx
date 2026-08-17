#!/usr/bin/env python3
"""Summarize a token-budgeted third-judge edge-disagreement calibration."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read_rated(path: Path, id_field: str = "edge_id") -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row[id_field]: row
        for row in rows
        if row.get(id_field) and row.get("rater_id", "").strip()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-left", type=Path, required=True)
    parser.add_argument("--legacy-right", type=Path, required=True)
    parser.add_argument("--third", type=Path, required=True)
    parser.add_argument("--rich-crosscheck", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    left = read_rated(args.legacy_left)
    right = read_rated(args.legacy_right)
    third = read_rated(args.third)
    mappings = {
        "biologically_meaningful": "relation_exists",
        "relation_type_correct": "relation_type_correct",
    }
    resolutions: dict[str, Counter] = {field: Counter() for field in mappings}
    majority_counts: dict[str, Counter] = {field: Counter() for field in mappings}
    eligible_disagreements = Counter()
    for edge_id, third_row in third.items():
        if edge_id not in left or edge_id not in right:
            continue
        for legacy_field, third_field in mappings.items():
            left_value = left[edge_id].get(legacy_field)
            right_value = right[edge_id].get(legacy_field)
            if left_value == right_value or left_value not in {"0", "1"} or right_value not in {"0", "1"}:
                continue
            eligible_disagreements[legacy_field] += 1
            third_value = third_row.get(third_field)
            if third_value == left_value:
                resolutions[legacy_field]["agrees_legacy_left"] += 1
            elif third_value == right_value:
                resolutions[legacy_field]["agrees_legacy_right"] += 1
            else:
                resolutions[legacy_field]["invalid_or_missing"] += 1
            majority_counts[legacy_field][third_value] += 1

    rich_fields = (
        "entity_valid",
        "relation_exists",
        "relation_type_correct",
        "direction_correct",
        "evidence_support",
    )
    third_rates = {
        field: round(sum(int(row[field]) for row in third.values()) / len(third), 4)
        for field in rich_fields
        if third and all(row.get(field) in {"0", "1"} for row in third.values())
    }

    crosscheck: dict[str, object] = {}
    if args.rich_crosscheck:
        other = read_rated(args.rich_crosscheck)
        shared = sorted(set(third) & set(other))
        crosscheck = {
            "shared_edges": len(shared),
            "exact_agreement": {
                field: round(
                    sum(third[eid].get(field) == other[eid].get(field) for eid in shared)
                    / len(shared),
                    4,
                )
                if shared
                else None
                for field in rich_fields
            },
        }

    payload = {
        "third_judge_rated_edges": len(third),
        "legacy_disagreements_in_sample": dict(eligible_disagreements),
        "third_judge_resolution": {field: dict(counts) for field, counts in resolutions.items()},
        "majority_label_among_disagreements": {
            field: dict(counts) for field, counts in majority_counts.items()
        },
        "third_judge_positive_rates": third_rates,
        "rich_rubric_crosscheck": crosscheck,
        "interpretation": (
            "Calibration sample only; deliberately enriched for legacy judge disagreements and "
            "must not be interpreted as whole-edge-population precision."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
