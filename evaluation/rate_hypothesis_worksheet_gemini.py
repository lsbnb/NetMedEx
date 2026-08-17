#!/usr/bin/env python3
"""Blind-rate hypothesis_ratings_worksheet.csv via the Google Gemini API.

Follows the same live-API/checkpoint/validation pattern as rate_ai_rater_3_api.py (formal_v2's
supplementary AI cross-check rater), adapted to the hypothesis/2-hop rubric in
formal/hypothesis_rating_instructions.md. This is a supplementary AI rating pass, not a human
expert review -- every note is tagged accordingly.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSHEET_PATH = BASE_DIR / "evaluation" / "formal" / "hypothesis_ratings_worksheet.csv"
CHECKPOINT_DIR = BASE_DIR / "evaluation" / "formal" / "hypothesis_rating_checkpoints"
MANIFEST_PATH = BASE_DIR / "evaluation" / "formal" / "hypothesis_rating_manifest.json"

MODEL = "gemini-3.1-pro-preview"
PREFIX = "[AI-GENERATED RATING -- Gemini 3.1 Pro. Blinded hypothesis/2-hop quality pass, not a human expert review.]"

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


def parse_json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        blob = match.group(1).strip()
        try:
            return json.loads(blob)
        except Exception:
            cleaned = re.sub(r",\s*([\]}])", r"\1", blob)
            return json.loads(cleaned)
    raise ValueError("Could not parse a JSON object from model response")


def validate_ratings(payload: dict, expected_ids: set[str]) -> list[dict]:
    ratings = payload.get("ratings")
    if not isinstance(ratings, list):
        raise ValueError("Response does not contain a ratings array")

    by_id: dict[str, dict] = {}
    for item in ratings:
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


def rate_question_via_gemini(
    api_key: str, question: str, rows: list[dict[str, str]], retries: int = 5
) -> tuple[list[dict], str]:
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code != 200:
                raise ValueError(f"API HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = parse_json_from_text(raw_text)
            expected_ids = {row["hypothesis_id"] for row in rows}
            validated = validate_ratings(parsed, expected_ids)
            return validated, raw_text
        except Exception as exc:
            last_err = exc
            print(f"  Attempt {attempt} failed: {exc}. Retrying...")
            time.sleep(3 * attempt)
    raise RuntimeError(f"Failed to rate question after {retries} attempts: {last_err}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    parser.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINT_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment or .env")

    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    with args.worksheet.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)

    by_question: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_question.setdefault(row["question_id"], []).append(row)

    row_by_hid = {row["hypothesis_id"]: row for row in rows}
    question_ids = sorted(by_question.keys())
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, qid in enumerate(question_ids, 1):
        q_rows = by_question[qid]
        question_text = q_rows[0]["question"]

        ckpt_path = args.checkpoint_dir / f"{qid}.json"
        if ckpt_path.exists():
            ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if ckpt.get("model") == MODEL and len(ckpt.get("ratings", [])) == len(q_rows):
                print(f"[{idx}/{len(question_ids)}] Skipping {qid} (already rated)", flush=True)
                ratings = ckpt["ratings"]
            else:
                ratings = None
        else:
            ratings = None

        if ratings is None:
            print(f"[{idx}/{len(question_ids)}] Rating {qid} ({len(q_rows)} answers)...", flush=True)
            ratings, raw_resp = rate_question_via_gemini(api_key, question_text, q_rows)
            ckpt_path.write_text(
                json.dumps(
                    {
                        "question_id": qid,
                        "model": MODEL,
                        "provider": "google",
                        "rated_at": datetime.now(timezone.utc).isoformat(),
                        "ratings": ratings,
                        "raw_response_sha256": hashlib.sha256(raw_resp.encode()).hexdigest(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            time.sleep(0.5)

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
        "provider": "google",
        "model": MODEL,
        "input_file": str(args.worksheet),
        "instructions_file": "evaluation/formal/hypothesis_rating_instructions.md",
        "started_at": now_iso,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "question_count": len(question_ids),
        "status": "complete",
        "notes": (
            "Blinded AI rating of the hypothesis/two_hop_path stratum's netmedex_hybrid_rag vs "
            "traditional_rag answers. Supplementary AI cross-check, not a human expert review."
        ),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. Rated {len(rows)} rows across {len(question_ids)} questions.")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
