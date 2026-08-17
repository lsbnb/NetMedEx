#!/usr/bin/env python3
"""Build a blinded path-qrels adjudication worksheet from replay path runs.

This intentionally leaves relevance and verification fields blank: surfaced model paths are
candidate evidence, not gold labels. A human adjudicator must complete the worksheet before it
is renamed/copied to a frozen ``path_qrels.csv`` and used for scoring.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

FIELDS = [
    "question_id", "path_id", "source", "bridge", "target", "relation_1", "relation_2",
    "direction_1", "direction_2", "pmids", "relevance", "path_type", "is_negative_control",
    "evidence_level_1", "evidence_level_2", "bridge_valid", "direction_verified", "notes",
]


def build_review_rows(input_dirs: list[Path]) -> list[dict[str, str]]:
    rows: dict[tuple[str, str, str, str, str, str, str, str], dict[str, str]] = {}
    for input_dir in input_dirs:
        with (input_dir / "path_runs.csv").open(newline="", encoding="utf-8") as handle:
            for item in csv.DictReader(handle):
                key = (
                    item.get("question_id", ""), item.get("source", ""), item.get("bridge", ""),
                    item.get("target", ""), item.get("relation_1", ""), item.get("relation_2", ""),
                    item.get("direction_1", ""), item.get("direction_2", ""),
                )
                if key in rows:
                    continue
                rows[key] = {
                    "question_id": item.get("question_id", ""),
                    "path_id": item.get("path_id", ""),
                    "source": item.get("source", ""),
                    "bridge": item.get("bridge", ""),
                    "target": item.get("target", ""),
                    "relation_1": item.get("relation_1", ""),
                    "relation_2": item.get("relation_2", ""),
                    "direction_1": item.get("direction_1", ""),
                    "direction_2": item.get("direction_2", ""),
                    "pmids": item.get("pmids", ""),
                    "relevance": "",
                    "path_type": "two_hop" if int(item.get("hop_count") or 0) == 2 else "one_hop",
                    "is_negative_control": "",
                    "evidence_level_1": "",
                    "evidence_level_2": "",
                    "bridge_valid": "",
                    "direction_verified": "",
                    "notes": "Candidate surfaced by replay; adjudicate against frozen corpus before scoring.",
                }
    return sorted(rows.values(), key=lambda row: (row["question_id"], row["path_type"], row["path_id"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_review_rows(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} candidate paths to {args.output}")


if __name__ == "__main__":
    main()
