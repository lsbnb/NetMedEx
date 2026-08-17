#!/usr/bin/env python3
"""Merge blinded reviews, calculate agreement, and export adjudicated qrels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


VALID_LABELS = {"0", "1", "2"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_label(value: str, candidate_id: str, source: str) -> str:
    label = value.strip()
    if label and label not in VALID_LABELS:
        raise ValueError(f"{source}: invalid relevance {label!r} for {candidate_id}")
    return label


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_counts = Counter(left for left, _right in pairs)
    right_counts = Counter(right for _left, right in pairs)
    expected = sum(
        left_counts[label] / len(pairs) * right_counts[label] / len(pairs)
        for label in VALID_LABELS
    )
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir", type=Path, default=Path("evaluation/formal_v2")
    )
    args = parser.parse_args()

    rater_1 = read_csv(args.input_dir / "expert_rater_1.csv")
    rater_2 = read_csv(args.input_dir / "expert_rater_2.csv")
    old_adjudication = {
        row["candidate_id"]: row
        for row in read_csv(args.input_dir / "adjudication.csv")
    }
    rater_2_by_id = {row["candidate_id"]: row for row in rater_2}
    if len(rater_1) != len(rater_2) or {row["candidate_id"] for row in rater_1} != set(
        rater_2_by_id
    ):
        raise ValueError("Rater worksheets do not contain identical candidate IDs")

    rows = []
    pairs: list[tuple[str, str]] = []
    completed_1 = 0
    completed_2 = 0
    final_count = 0
    for left in rater_1:
        candidate_id = left["candidate_id"]
        right = rater_2_by_id[candidate_id]
        label_1 = validate_label(left["relevance"], candidate_id, "rater 1")
        label_2 = validate_label(right["relevance"], candidate_id, "rater 2")
        completed_1 += bool(label_1)
        completed_2 += bool(label_2)
        agreement = ""
        if label_1 and label_2:
            pairs.append((label_1, label_2))
            agreement = "yes" if label_1 == label_2 else "no"

        previous = old_adjudication.get(candidate_id, {})
        previous_final = validate_label(
            previous.get("adjudicated_relevance", ""), candidate_id, "adjudication"
        )
        final_label = previous_final or (
            label_1 if label_1 and label_1 == label_2 else ""
        )
        final_count += bool(final_label)
        rows.append(
            {
                "candidate_id": candidate_id,
                "question_id": left["question_id"],
                "pmid": left["pmid"],
                "rater_1_relevance": label_1,
                "rater_2_relevance": label_2,
                "agreement": agreement,
                "adjudicated_relevance": final_label,
                "adjudicator_id": previous.get("adjudicator_id", ""),
                "adjudication_notes": previous.get("adjudication_notes", ""),
            }
        )

    fields = [
        "candidate_id",
        "question_id",
        "pmid",
        "rater_1_relevance",
        "rater_2_relevance",
        "agreement",
        "adjudicated_relevance",
        "adjudicator_id",
        "adjudication_notes",
    ]
    write_csv(args.input_dir / "adjudication.csv", fields, rows)

    raw_agreement = (
        sum(left == right for left, right in pairs) / len(pairs) if pairs else None
    )
    summary = {
        "candidate_count": len(rows),
        "rater_1_completed": completed_1,
        "rater_2_completed": completed_2,
        "double_rated_count": len(pairs),
        "raw_agreement": round(raw_agreement, 4) if raw_agreement is not None else None,
        "cohen_kappa": round(cohen_kappa(pairs), 4) if pairs else None,
        "adjudicated_count": final_count,
        "disagreement_count": sum(left != right for left, right in pairs),
        "status": "complete" if final_count == len(rows) else "review_in_progress",
    }

    status_path = args.input_dir / "review_status.csv"
    if status_path.exists():
        status_rows = read_csv(status_path)
        rows_by_question: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            rows_by_question.setdefault(row["question_id"], []).append(row)
        for status_row in status_rows:
            question_rows = rows_by_question.get(status_row["question_id"], [])
            status_row["rater_1_status"] = (
                "complete"
                if question_rows
                and all(row["rater_1_relevance"] for row in question_rows)
                else "pending"
            )
            status_row["rater_2_status"] = (
                "complete"
                if question_rows
                and all(row["rater_2_relevance"] for row in question_rows)
                else "pending"
            )
            status_row["adjudication_status"] = (
                "complete"
                if question_rows
                and all(row["adjudicated_relevance"] for row in question_rows)
                else "pending"
            )
        write_csv(status_path, list(status_rows[0]), status_rows)

    if final_count == len(rows):
        qrels_path = args.input_dir / "qrels.csv"
        write_csv(
            qrels_path,
            ["question_id", "pmid", "relevance"],
            [
                {
                    "question_id": row["question_id"],
                    "pmid": row["pmid"],
                    "relevance": row["adjudicated_relevance"],
                }
                for row in rows
            ],
        )
        summary["qrels_sha256"] = hashlib.sha256(qrels_path.read_bytes()).hexdigest()

    (args.input_dir / "review_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
