#!/usr/bin/env python3
"""Freeze an endpoint-distinct internal validation set before D-v3 evaluation."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_Q = ROOT / "evaluation/formal/questions.csv"
SOURCE_QUERY = ROOT / "evaluation/formal/formal_run_queries.csv"
OUTPUT = ROOT / "evaluation/formal/internal_locked_30_v1"

# Fixed stratified selection from questions excluded from path-positive-20 development.
IDS = [
    "Q003", "Q013", "Q021", "Q027", "Q033", "Q046",  # direct incl. negative control
    "Q016", "Q022", "Q023", "Q029", "Q031",            # mechanism
    "Q002", "Q009", "Q014", "Q017", "Q049",            # retrieval
    "Q012", "Q019", "Q026", "Q032",                     # association
    "Q018", "Q025", "Q040",                              # hypothesis
    "Q015", "Q028", "Q035",                              # two-hop
    "Q043", "Q044",                                       # cross-species
    "Q010", "Q041",                                       # multilingual mechanism
]


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    q = {row["question_id"]: row for row in read(SOURCE_Q)}
    query = {row["question_id"]: row for row in read(SOURCE_QUERY)}
    if len(IDS) != 30 or len(set(IDS)) != 30:
        raise RuntimeError("Locked set must contain exactly 30 unique IDs")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write(OUTPUT / "questions.csv", [q[item] for item in IDS])
    write(OUTPUT / "queries.csv", [query[item] for item in IDS])
    manifest = {
        "benchmark_id": "internal-locked-30-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "frozen_before_dv3_judging": True,
        "selection_used_system_answers_or_judge_scores": False,
        "purpose": "internal locked ITT validation including zero-path questions",
        "limitations": [
            "Questions originate from the historical formal-50 bank and are not a clean external holdout.",
            "Use a new curator/domain/time-window cohort for confirmatory publication claims.",
        ],
        "question_ids": IDS,
        "questions_sha256": sha(OUTPUT / "questions.csv"),
        "queries_sha256": sha(OUTPUT / "queries.csv"),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
