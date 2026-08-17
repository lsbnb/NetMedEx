#!/usr/bin/env python3
"""Select only cross-judge disagreements for token-efficient independent adjudication."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_by_id(path: Path, id_field: str) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = {row[id_field]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {id_field} values in {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--id-field", default="edge_id")
    parser.add_argument("--field", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument(
        "--per-question",
        type=int,
        default=0,
        help="Optional cap per question before applying --max-items.",
    )
    args = parser.parse_args()
    left = read_by_id(args.left, args.id_field)
    right = read_by_id(args.right, args.id_field)
    shared = sorted(set(left) & set(right))
    selected = [
        item_id
        for item_id in shared
        if any(left[item_id].get(field) != right[item_id].get(field) for field in args.field)
    ]
    if args.per_question > 0:
        by_question: dict[str, list[str]] = defaultdict(list)
        for item_id in selected:
            by_question[item_id.rsplit("-", 1)[0]].append(item_id)
        selected = [
            item_id
            for question_id in sorted(by_question)
            for item_id in by_question[question_id][: args.per_question]
        ]
    if args.max_items > 0:
        selected = selected[: args.max_items]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(selected) + ("\n" if selected else ""), encoding="utf-8")
    print(f"Selected {len(selected)} disagreements from {len(shared)} shared items")
    print(args.output)


if __name__ == "__main__":
    main()
