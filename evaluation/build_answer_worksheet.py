#!/usr/bin/env python3
"""Build a reproducibly blinded Hybrid-vs-Text answer worksheet and private key."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

DEFAULT_SYSTEMS = ("netmedex_hybrid_rag", "traditional_rag")
FIELDS = [
    "question_id",
    "question_type",
    "domain",
    "question",
    "answer_id",
    "answer_text",
    "rater_id",
    "correctness",
    "completeness",
    "relevance",
    "grounding",
    "mechanistic_coherence",
    "research_value",
    "preferred_answer_id",
    "pairwise_reason",
    "notes",
]
KEY_FIELDS = ["answer_id", "question_id", "system"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def build(
    questions_path: Path,
    system_outputs_path: Path,
    worksheet_path: Path,
    key_path: Path,
    seed: int = 42,
    systems: tuple[str, ...] = DEFAULT_SYSTEMS,
) -> tuple[int, int]:
    questions = {row["question_id"]: row for row in read_csv(questions_path)}
    outputs = {
        (row["question_id"], row["system"]): row["answer"]
        for row in read_csv(system_outputs_path)
        if row.get("system") in systems
    }
    qids = sorted(
        qid
        for qid in questions
        if all(outputs.get((qid, system), "").strip() for system in systems)
    )
    if not qids:
        raise ValueError("No questions have complete Hybrid and Text-RAG answers")

    existing: dict[str, dict[str, str]] = {}
    if key_path.exists():
        for row in read_csv(key_path):
            label = row["answer_id"].rsplit("-", 1)[-1]
            existing.setdefault(row["question_id"], {})[label] = row["system"]

    worksheet_rows: list[dict[str, str]] = []
    key_rows: list[dict[str, str]] = []
    for qid in qids:
        question = questions[qid]
        labels = tuple(chr(ord("A") + index) for index in range(len(systems)))
        if qid in existing and set(existing[qid]) == set(labels):
            assignment = existing[qid]
        else:
            shuffled_systems = list(systems)
            random.Random(f"{seed}:{qid}:answer-panel").shuffle(shuffled_systems)
            assignment = dict(zip(labels, shuffled_systems))
        for label, system in sorted(assignment.items()):
            answer_id = f"{qid}-{label}"
            worksheet_rows.append(
                {
                    "question_id": qid,
                    "question_type": question.get("question_type", ""),
                    "domain": question.get("domain", ""),
                    "question": question["question"],
                    "answer_id": answer_id,
                    "answer_text": outputs[(qid, system)],
                    "rater_id": "",
                    "correctness": "",
                    "completeness": "",
                    "relevance": "",
                    "grounding": "",
                    "mechanistic_coherence": "",
                    "research_value": "",
                    "preferred_answer_id": "",
                    "pairwise_reason": "",
                    "notes": "",
                }
            )
            key_rows.append({"answer_id": answer_id, "question_id": qid, "system": system})

    write_csv(worksheet_path, FIELDS, worksheet_rows)
    write_csv(key_path, KEY_FIELDS, key_rows)
    return len(qids), len(worksheet_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("evaluation/formal/questions.csv"))
    parser.add_argument(
        "--system-outputs",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/system_outputs.csv"),
    )
    parser.add_argument(
        "--worksheet",
        type=Path,
        default=Path("evaluation/formal/answer_ratings_worksheet.csv"),
    )
    parser.add_argument(
        "--key", type=Path, default=Path("evaluation/formal/answer_ratings_key.csv")
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--include-general-llm",
        action="store_true",
        help="Blind and rate General LLM alongside Hybrid and Traditional RAG (A/B/C).",
    )
    parser.add_argument(
        "--system",
        action="append",
        default=[],
        help="System label to blind; repeat for a custom multi-arm worksheet.",
    )
    args = parser.parse_args()
    systems = tuple(args.system) or (
        DEFAULT_SYSTEMS + (("general_llm",) if args.include_general_llm else ())
    )
    questions, rows = build(
        args.questions, args.system_outputs, args.worksheet, args.key, args.seed, systems
    )
    print(f"Wrote {rows} blinded answer rows for {questions} questions")
    print(f"Worksheet: {args.worksheet}")
    print(f"Private key: {args.key}")


if __name__ == "__main__":
    main()
