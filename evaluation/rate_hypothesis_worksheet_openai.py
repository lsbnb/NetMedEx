#!/usr/bin/env python3
"""Blind-rate a hypothesis worksheet via OpenAI, as a second independent AI rater.

Mirrors rate_hypothesis_worksheet_gemini.py's rubric and blinding rules but calls OpenAI
gpt-5.6-sol (the same model already used elsewhere in this pipeline as an independent rater/
adjudicator) via the chat.completions API, matching adjudicate_ai_disagreements.py's call pattern.
Operates on its own worksheet copy so it never overwrites the Gemini rater's completed pass.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_WORKSHEET = Path("evaluation/formal/hypothesis_ratings_worksheet_openai.csv")
DEFAULT_MANIFEST = Path("evaluation/formal/hypothesis_rating_manifest_openai.json")
MODEL = "gpt-5.6-sol"

PREFIX = "[AI-GENERATED RATING -- GPT-5.6-sol. Blinded hypothesis/2-hop quality pass, not a human expert review.]"

SYSTEM_PROMPT = """You are a biomedical research reviewer scoring generated answers for hypothesis
quality. You are blinded to which retrieval system produced each answer -- do not try to guess,
and do not let a guess affect your score.

For each answer, score four dimensions on a 1-5 integer scale:
- novelty: does the answer surface a non-obvious connection, or just restate common knowledge?
- plausibility: is the proposed mechanism/link biologically credible given what is stated?
- testability: could a lab feasibly design an experiment to confirm or refute this?
- research_value: would a working researcher find this worth following up?

Judge relevance/quality of the content itself, not writing style or length. Leave no dimension
unscored -- if the answer text gives weak basis to judge a dimension, still give your best-supported
integer score rather than omitting it, and say why in notes."""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def rate_question(
    client: OpenAI, question: str, rows: list[dict[str, str]]
) -> list[dict]:
    records = [
        {"hypothesis_id": row["hypothesis_id"], "answer_text": row["answer_text"]}
        for row in rows
    ]
    user_prompt = (
        f"Question:\n{question}\n\n"
        "Score every answer below. Return a JSON object with key `ratings`, an array with exactly "
        "one object per answer, each containing `hypothesis_id` (string, echoed back unchanged), "
        "`novelty`, `plausibility`, `testability`, `research_value` (each an integer 1-5), and "
        "`notes` (concise justification citing something specific in the answer text).\n\n"
        f"Answers:\n{json.dumps(records, ensure_ascii=False)}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1,
        max_completion_tokens=4000,
        response_format={"type": "json_object"},
        timeout=300,
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        raise ValueError("Rater returned an empty response")
    payload = json.loads(content)
    items = payload.get("ratings")
    if not isinstance(items, list):
        raise ValueError("Response lacks a ratings array")

    expected_ids = {row["hypothesis_id"] for row in rows}
    by_id: dict[str, dict] = {}
    for item in items:
        hid = str(item.get("hypothesis_id", "")).strip()
        if hid in by_id:
            raise ValueError(f"Duplicate hypothesis_id: {hid}")
        scores = {}
        for field in ("novelty", "plausibility", "testability", "research_value"):
            value = item.get(field)
            if not isinstance(value, int) or not (1 <= value <= 5):
                raise ValueError(f"[{hid}] invalid {field}: {value!r}")
            scores[field] = value
        note = str(item.get("notes", "")).strip()
        if not note.startswith("[AI-GENERATED RATING"):
            note = f"{PREFIX} {note}"
        by_id[hid] = {"hypothesis_id": hid, **scores, "notes": note}

    if set(by_id.keys()) != expected_ids:
        missing = sorted(expected_ids - set(by_id.keys()))
        extra = sorted(set(by_id.keys()) - expected_ids)
        raise ValueError(f"hypothesis_id mismatch. Missing: {missing}, Extra: {extra}")
    return [by_id[hid] for hid in sorted(by_id.keys())]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=api_key)

    fieldnames, rows = read_csv(args.worksheet)
    by_question: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_question.setdefault(row["question_id"], []).append(row)
    row_by_hid = {row["hypothesis_id"]: row for row in rows}
    question_ids = sorted(by_question.keys())
    started_at = datetime.now(timezone.utc).isoformat()

    for idx, qid in enumerate(question_ids, 1):
        q_rows = by_question[qid]
        print(f"[{idx}/{len(question_ids)}] Rating {qid} ({len(q_rows)} answers) via {MODEL}...", flush=True)
        ratings = rate_question(client, q_rows[0]["question"], q_rows)
        for rating in ratings:
            entry = row_by_hid[rating["hypothesis_id"]]
            entry["rater_id"] = MODEL
            entry["novelty"] = str(rating["novelty"])
            entry["plausibility"] = str(rating["plausibility"])
            entry["testability"] = str(rating["testability"])
            entry["research_value"] = str(rating["research_value"])
            entry["notes"] = rating["notes"]

    tmp = args.worksheet.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(args.worksheet)

    manifest = {
        "reviewer_type": "AI",
        "role": "supplementary_hypothesis_quality_rater",
        "provider": "openai",
        "model": MODEL,
        "input_file": str(args.worksheet),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "question_count": len(question_ids),
        "status": "complete",
        "notes": (
            "Second, independent blinded AI rater for the hypothesis/two_hop_path stratum "
            "(cross-check against the Gemini 3.1 Pro pass). Supplementary AI rating, not a "
            "human expert review."
        ),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. Rated {len(rows)} rows across {len(question_ids)} questions.")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
