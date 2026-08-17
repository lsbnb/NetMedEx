#!/usr/bin/env python3
"""Blind-rate pooled relevance candidates with an OpenAI model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


SYSTEM_PROMPT = """You are a biomedical information-retrieval relevance assessor.
Judge each PubMed article only against the supplied question. You are blinded to retrieval system,
rank, score, and prior labels.

Relevance labels:
2 = directly addresses the requested entity relationship, mechanism, intervention, disease context,
population, or study type.
1 = useful adjacent evidence, review-level context, a different but informative model, or one
supported segment of a multi-hop mechanism.
0 = off-topic, wrong entity/context/study type, too broad, or keyword overlap without support.

For negative-control questions asking whether direct evidence exists, assign 2 only if the exact
direct causal or mechanistic link is tested. Biological plausibility alone is not direct evidence.

Confidence:
3 = clear from title/abstract; 2 = some ambiguity; 1 = full text or specialist adjudication needed.

For relevance 0, exclusion_reason must be one of: off_topic, wrong_entity, wrong_context,
wrong_study_type, too_broad, no_usable_evidence, duplicate, other. For relevance 1 or 2, use an
empty exclusion_reason. Return concise reviewer_notes grounded in the supplied record. Do not use
outside knowledge to invent evidence."""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def build_user_prompt(question: str, candidates: list[dict[str, str]]) -> str:
    records = [
        {
            "candidate_id": row["candidate_id"],
            "pmid": row["pmid"],
            "title": row["title"],
            "abstract": row["abstract"] or "[No abstract available]",
        }
        for row in candidates
    ]
    return (
        f"Question:\n{question}\n\n"
        "Assess every candidate below. Return a JSON object with key `ratings`, whose value is an "
        "array containing exactly one object per candidate. Each object must contain "
        "`candidate_id`, integer `relevance` (0, 1, or 2), integer `confidence` (1, 2, or 3), "
        "string `exclusion_reason`, and string `reviewer_notes`.\n\n"
        f"Candidates:\n{json.dumps(records, ensure_ascii=False)}"
    )


def validate_ratings(
    payload: dict[str, Any], expected_ids: set[str]
) -> list[dict[str, Any]]:
    ratings = payload.get("ratings")
    if not isinstance(ratings, list):
        raise ValueError("Response does not contain a ratings array")
    by_id: dict[str, dict[str, Any]] = {}
    allowed_reasons = {
        "",
        "off_topic",
        "wrong_entity",
        "wrong_context",
        "wrong_study_type",
        "too_broad",
        "no_usable_evidence",
        "duplicate",
        "other",
    }
    for rating in ratings:
        if not isinstance(rating, dict):
            raise ValueError("Rating entry is not an object")
        candidate_id = str(rating.get("candidate_id", ""))
        relevance = rating.get("relevance")
        confidence = rating.get("confidence")
        reason = str(rating.get("exclusion_reason", "")).strip()
        if candidate_id in by_id:
            raise ValueError(f"Duplicate candidate ID: {candidate_id}")
        if relevance not in {0, 1, 2}:
            raise ValueError(f"Invalid relevance for {candidate_id}: {relevance}")
        if confidence not in {1, 2, 3}:
            raise ValueError(f"Invalid confidence for {candidate_id}: {confidence}")
        if reason not in allowed_reasons:
            raise ValueError(f"Invalid exclusion reason for {candidate_id}: {reason}")
        if relevance == 0 and not reason:
            raise ValueError(f"Missing exclusion reason for {candidate_id}")
        if relevance > 0:
            reason = ""
        by_id[candidate_id] = {
            "candidate_id": candidate_id,
            "relevance": relevance,
            "confidence": confidence,
            "exclusion_reason": reason,
            "reviewer_notes": str(rating.get("reviewer_notes", "")).strip(),
        }
    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        extra = sorted(set(by_id) - expected_ids)
        raise ValueError(f"Candidate mismatch; missing={missing}, extra={extra}")
    return [by_id[candidate_id] for candidate_id in sorted(by_id)]


def rate_question(
    client: OpenAI,
    model: str,
    question: str,
    candidates: list[dict[str, str]],
    retries: int = 3,
) -> tuple[list[dict[str, Any]], str]:
    user_prompt = build_user_prompt(question, candidates)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=1,
                max_completion_tokens=12000,
                response_format={"type": "json_object"},
                timeout=600,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise ValueError("Model returned an empty response")
            payload = json.loads(content)
            ratings = validate_ratings(
                payload, {row["candidate_id"] for row in candidates}
            )
            return ratings, content
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(15 * attempt)
    raise RuntimeError(f"Rating failed after {retries} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("evaluation/formal_v2/expert_rater_2.csv"),
    )
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=api_key)

    fieldnames, rows = read_csv(args.input)
    required = {
        "candidate_id",
        "question_id",
        "question",
        "pmid",
        "title",
        "abstract",
        "relevance",
        "confidence",
        "exclusion_reason",
        "reviewer_notes",
    }
    if not required.issubset(fieldnames):
        raise ValueError(f"Input is missing columns: {sorted(required - set(fieldnames))}")

    by_question: dict[str, list[dict[str, str]]] = defaultdict(list)
    all_rows_by_question: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        all_rows_by_question[row["question_id"]].append(row)
        if args.only and row["question_id"] not in set(args.only):
            continue
        if args.overwrite or not row["relevance"].strip():
            by_question[row["question_id"]].append(row)

    checkpoint_dir = args.input.parent / f"{args.input.stem}_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.input.parent / f"{args.input.stem}_manifest.json"
    existing_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "reviewer_type": "AI",
        "provider": "openai",
        "model": args.model,
        "input_file": str(args.input),
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "blinded_fields": ["system", "rank", "score", "prior_relevance", "provenance"],
        "started_at": existing_manifest.get("started_at", now),
        "status": "running",
        "completed_questions": sum(
            all(item["relevance"].strip() for item in question_rows)
            for question_rows in all_rows_by_question.values()
        ),
        "completed_candidates": sum(bool(row["relevance"].strip()) for row in rows),
    }
    atomic_json(manifest_path, manifest)

    row_by_id = {row["candidate_id"]: row for row in rows}
    completed_questions = 0
    try:
        for question_id in sorted(by_question):
            candidates = by_question[question_id]
            print(f"Rating {question_id}: {len(candidates)} candidates", flush=True)
            ratings, raw_response = rate_question(
                client,
                args.model,
                candidates[0]["question"],
                candidates,
            )
            for rating in ratings:
                row = row_by_id[rating["candidate_id"]]
                row["relevance"] = str(rating["relevance"])
                row["confidence"] = str(rating["confidence"])
                row["exclusion_reason"] = rating["exclusion_reason"]
                row["reviewer_notes"] = rating["reviewer_notes"]
            atomic_write_csv(args.input, fieldnames, rows)
            atomic_json(
                checkpoint_dir / f"{question_id}.json",
                {
                    "question_id": question_id,
                    "model": args.model,
                    "rated_at": datetime.now(timezone.utc).isoformat(),
                    "ratings": ratings,
                    "raw_response_sha256": hashlib.sha256(
                        raw_response.encode()
                    ).hexdigest(),
                },
            )
            completed_questions += 1
            manifest["completed_questions"] = sum(
                all(item["relevance"].strip() for item in question_rows)
                for question_rows in all_rows_by_question.values()
            )
            manifest["completed_candidates"] = sum(
                bool(row["relevance"].strip()) for row in rows
            )
            manifest["last_checkpoint_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(manifest_path, manifest)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["failed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(manifest_path, manifest)
        raise

    checkpoint_times = []
    for checkpoint_path in checkpoint_dir.glob("Q*.json"):
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("model") == args.model and checkpoint.get("rated_at"):
            checkpoint_times.append(checkpoint["rated_at"])
    if checkpoint_times:
        manifest["first_checkpoint_at"] = min(checkpoint_times)
        manifest["last_checkpoint_at"] = max(checkpoint_times)
        if not by_question:
            manifest["started_at"] = min(checkpoint_times)
    manifest["status"] = "complete"
    manifest["completed_at"] = (
        datetime.now(timezone.utc).isoformat()
        if by_question
        else max(checkpoint_times)
        if checkpoint_times
        else existing_manifest.get("completed_at", now)
    )
    atomic_json(manifest_path, manifest)
    print(
        f"Completed {manifest['completed_candidates']}/{len(rows)} candidate ratings",
        flush=True,
    )


if __name__ == "__main__":
    main()
