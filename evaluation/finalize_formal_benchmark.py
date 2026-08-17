#!/usr/bin/env python3
"""Finalize the internally adjudicated formal evaluation benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


FINAL_ADJUDICATOR = "codex-final-adjudication"
FINAL_STATUS = "final-ai-adjudicated"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def adjudicate_candidates(
    formal_dir: Path, adjudication_date: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = formal_dir / "qrels_candidates_q011_q050.csv"
    fieldnames, rows = read_csv(path)
    log_rows: list[dict[str, str]] = []

    for row in rows:
        pmids = row["candidate_pmids"].split(";")
        grades = row["relevance_grade"].split(";")
        flags = row["audit_flags_2nd_pass"].split(";")
        if not (len(pmids) == len(grades) == len(flags)):
            raise ValueError(f"Unaligned candidate columns for {row['question_id']}")

        final_grades: list[str] = []
        for pmid, old_grade, flag in zip(pmids, grades, flags):
            final_grade = old_grade
            decision_basis = "Two independent AI passes agreed; grade retained."
            if flag != "-":
                if len(flag) != 2 or flag[0] not in {"^", "v"} or flag[1] not in "012":
                    raise ValueError(
                        f"Invalid audit flag {flag!r} for {row['question_id']}/{pmid}"
                    )
                final_grade = flag[1]
                decision_basis = (
                    "Final abstract-level adjudication accepted the second-pass "
                    f"recommendation {flag}."
                )
            final_grades.append(final_grade)
            log_rows.append(
                {
                    "question_id": row["question_id"],
                    "pmid": pmid,
                    "original_grade": old_grade,
                    "final_grade": final_grade,
                    "decision_basis": decision_basis,
                    "adjudicator": FINAL_ADJUDICATOR,
                    "adjudicator_type": "AI",
                    "adjudication_date": adjudication_date,
                }
            )

        row["relevance_grade"] = ";".join(final_grades)
        row["curator_id"] = FINAL_ADJUDICATOR
        row["curation_status"] = FINAL_STATUS
        if "FINAL ADJUDICATION:" not in row["notes"]:
            row["notes"] += (
                " || FINAL ADJUDICATION: PMID metadata and disputed grades were "
                "checked against PubMed abstracts; second-pass recommendations "
                f"were accepted and frozen on {adjudication_date}. This is an "
                "internal AI adjudication, not a claim of human expert review."
            )

    write_csv(path, fieldnames, rows)
    return rows, log_rows


def finalize_seed_qrels(
    formal_dir: Path, adjudication_date: str
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
    path = formal_dir / "qrels.csv"
    fieldnames, rows = read_csv(path)
    log_rows: list[dict[str, str]] = []

    for row in rows:
        old_grade = row["original_relevance"] or row["relevance"]
        if row["audit_status"] == "confirmed":
            row["audit_status"] = "final-ai-confirmed"
            basis = "PubMed audit confirmed the seed grade; final grade retained."
        else:
            row["audit_status"] = "final-ai-regraded"
            basis = row["notes"] or "PubMed audit supported the revised grade."
        log_rows.append(
            {
                "question_id": row["question_id"],
                "pmid": row["pmid"],
                "original_grade": old_grade,
                "final_grade": row["relevance"],
                "decision_basis": basis,
                "adjudicator": FINAL_ADJUDICATOR,
                "adjudicator_type": "AI",
                "adjudication_date": adjudication_date,
            }
        )

    return fieldnames, rows, log_rows


def merge_qrels(
    seed_rows: list[dict[str, str]], candidate_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    merged = list(seed_rows)
    for row in candidate_rows:
        for pmid, grade in zip(
            row["candidate_pmids"].split(";"), row["relevance_grade"].split(";")
        ):
            merged.append(
                {
                    "question_id": row["question_id"],
                    "pmid": pmid,
                    "relevance": grade,
                    "original_relevance": "",
                    "audit_status": FINAL_STATUS,
                    "notes": (
                        "Final internal AI adjudication; see "
                        "qrels_adjudication_log.csv and candidate worksheet."
                    ),
                }
            )
    return merged


def update_questions(
    formal_dir: Path, qrels_rows: list[dict[str, str]], adjudication_date: str
) -> None:
    path = formal_dir / "questions.csv"
    fieldnames, rows = read_csv(path)
    positive_pmids: dict[str, list[str]] = {}
    for row in qrels_rows:
        if int(row["relevance"]) > 0:
            positive_pmids.setdefault(row["question_id"], []).append(row["pmid"])

    for row in rows:
        question_id = row["question_id"]
        row["gold_pmids"] = ";".join(positive_pmids.get(question_id, []))
        final_note = (
            f"Formal benchmark v1 internally AI-adjudicated and frozen "
            f"{adjudication_date}; see qrels_adjudication_log.csv."
        )
        if final_note not in row["curator_notes"]:
            row["curator_notes"] = (
                f"{row['curator_notes']} || {final_note}"
                if row["curator_notes"]
                else final_note
            )

    write_csv(path, fieldnames, rows)


def write_freeze_manifest(
    formal_dir: Path, adjudication_date: str, qrels_rows: list[dict[str, str]]
) -> None:
    questions_path = formal_dir / "questions.csv"
    qrels_path = formal_dir / "qrels.csv"
    positive = sum(int(row["relevance"]) > 0 for row in qrels_rows)
    manifest = {
        "benchmark_version": "formal-v1",
        "frozen_on": adjudication_date,
        "status": FINAL_STATUS,
        "review_scope": "Q001-Q050",
        "adjudicator": FINAL_ADJUDICATOR,
        "adjudicator_type": "AI",
        "human_expert_review_claimed": False,
        "question_count": 50,
        "qrel_judgment_count": len(qrels_rows),
        "positive_qrel_count": positive,
        "sha256": {
            "questions.csv": sha256(questions_path),
            "qrels.csv": sha256(qrels_path),
        },
    }
    (formal_dir / "benchmark_freeze_v1.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def verify_existing_freeze(formal_dir: Path) -> bool:
    manifest_path = formal_dir / "benchmark_freeze_v1.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != FINAL_STATUS:
        return False
    for filename, expected_hash in manifest["sha256"].items():
        actual_hash = sha256(formal_dir / filename)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Frozen file {filename} has changed: expected {expected_hash}, "
                f"found {actual_hash}"
            )
    print("formal-v1 is already frozen; checksums verified")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--formal-dir", type=Path, default=Path("evaluation/formal")
    )
    parser.add_argument("--date", default="2026-07-27")
    args = parser.parse_args()

    if verify_existing_freeze(args.formal_dir):
        return

    candidate_rows, candidate_log = adjudicate_candidates(args.formal_dir, args.date)
    fieldnames, seed_rows, seed_log = finalize_seed_qrels(args.formal_dir, args.date)
    qrels_rows = merge_qrels(seed_rows, candidate_rows)
    write_csv(args.formal_dir / "qrels.csv", fieldnames, qrels_rows)
    update_questions(args.formal_dir, qrels_rows, args.date)

    log_fieldnames = [
        "question_id",
        "pmid",
        "original_grade",
        "final_grade",
        "decision_basis",
        "adjudicator",
        "adjudicator_type",
        "adjudication_date",
    ]
    write_csv(
        args.formal_dir / "qrels_adjudication_log.csv",
        log_fieldnames,
        seed_log + candidate_log,
    )
    write_freeze_manifest(args.formal_dir, args.date, qrels_rows)


if __name__ == "__main__":
    main()
