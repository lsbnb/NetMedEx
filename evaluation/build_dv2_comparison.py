#!/usr/bin/env python3
"""Build B/C/legacy-D/structured-D comparison outputs from completed checkpoints."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abcd", type=Path, required=True)
    parser.add_argument("--dv2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for row in read_csv(args.abcd):
        arm = row["arm"]
        if arm in {"B", "C", "D"}:
            system = {
                "B": "traditional_text_rag",
                "C": "text_rag_kg_reranking",
                "D": "legacy_path_answer",
            }[arm]
            rows.append({"question_id": row["question_id"], "system": system, "answer": row["answer"]})
    for row in read_csv(args.dv2):
        rows.append(
            {
                "question_id": row["question_id"],
                "system": "structured_gated_path_answer",
                "answer": row["answer"],
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question_id", "system", "answer"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} answers")


if __name__ == "__main__":
    main()
