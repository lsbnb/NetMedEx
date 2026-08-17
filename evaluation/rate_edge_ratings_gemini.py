#!/usr/bin/env python3
"""Blind-rate edge_ratings_worksheet.csv via the Google Gemini API.

Unlike hypothesis rating, there is no system to blind here -- every edge came from
netmedex_hybrid_rag's own graph (Traditional RAG has no graph). This audits whether the
extracted (source, target, relation_type) edges are biologically meaningful and whether the
relation label is correct, grounded in the supporting article titles.
"""

from __future__ import annotations

import argparse
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

DEFAULT_WORKSHEET = Path("evaluation/formal/edge_ratings_worksheet.csv")
DEFAULT_CHECKPOINT_DIR = Path("evaluation/formal/edge_rating_checkpoints_gemini")
DEFAULT_MANIFEST = Path("evaluation/formal/edge_rating_manifest_gemini.json")

MODEL = "gemini-3.1-pro-preview"
PREFIX = "[AI-GENERATED RATING -- Gemini 3.1 Pro. Blinded graph-edge quality pass, not a human expert review.]"

SYSTEM_PROMPT = """You are a biomedical knowledge-graph auditor. You are reviewing edges that a
graph-based retrieval system (NetMedEx) automatically extracted between two named entities using an
LLM-based semantic relation extractor over PubMed abstracts. For each edge, judge two things:

- biologically_meaningful (0 or 1): is it biologically plausible that source and target are
  related at all, given the supporting article titles? 0 if the relation looks spurious, a
  co-occurrence artifact, or unsupported by the titles.
- relation_type_correct (0 or 1): does the specific relation label (e.g. "inhibits", "upregulates",
  "treats", "ameliorates") correctly characterize the direction/nature of the relationship implied
  by the supporting titles? 0 if the direction or nature is wrong even if some relation exists.

Ground every judgment in the supplied supporting_titles -- do not use outside knowledge to invent
support the titles don't show, but domain background knowledge is fine for judging plausibility."""


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
        eid = str(item.get("edge_id", "")).strip()
        if eid in by_id:
            raise ValueError(f"Duplicate edge_id: {eid}")
        bio = item.get("biologically_meaningful")
        rel = item.get("relation_type_correct")
        if bio not in (0, 1):
            raise ValueError(f"[{eid}] invalid biologically_meaningful: {bio!r}")
        if rel not in (0, 1):
            raise ValueError(f"[{eid}] invalid relation_type_correct: {rel!r}")
        note = str(item.get("notes", "")).strip()
        if not note.startswith("[AI-GENERATED RATING"):
            note = f"{PREFIX} {note}"
        by_id[eid] = {
            "edge_id": eid,
            "biologically_meaningful": bio,
            "relation_type_correct": rel,
            "notes": note,
        }

    if set(by_id.keys()) != expected_ids:
        missing = sorted(expected_ids - set(by_id.keys()))
        extra = sorted(set(by_id.keys()) - expected_ids)
        raise ValueError(f"edge_id mismatch. Missing: {missing}, Extra: {extra}")
    return [by_id[eid] for eid in sorted(by_id.keys())]


def rate_question_via_gemini(
    api_key: str, question: str, rows: list[dict[str, str]], retries: int = 5
) -> tuple[list[dict], str]:
    records = [
        {
            "edge_id": row["edge_id"],
            "source": row["source"],
            "target": row["target"],
            "relation_type": row["relation_type"],
            "supporting_titles": row["supporting_titles"],
        }
        for row in rows
    ]
    user_prompt = (
        f"Question the graph was built to help answer:\n{question}\n\n"
        "Audit every edge below. Return a JSON object with key `ratings`, an array with exactly "
        "one object per edge, each containing `edge_id` (string, echoed back unchanged), "
        "`biologically_meaningful` (integer 0 or 1), `relation_type_correct` (integer 0 or 1), and "
        "`notes` (concise justification citing the supporting titles).\n\n"
        f"Edges:\n{json.dumps(records, ensure_ascii=False)}"
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
            expected_ids = {row["edge_id"] for row in rows}
            validated = validate_ratings(parsed, expected_ids)
            return validated, raw_text
        except Exception as exc:
            last_err = exc
            print(f"  Attempt {attempt} failed: {exc}. Retrying...")
            time.sleep(3 * attempt)
    raise RuntimeError(f"Failed to rate question after {retries} attempts: {last_err}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
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

    row_by_eid = {row["edge_id"]: row for row in rows}
    question_ids = sorted(by_question.keys())
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, qid in enumerate(question_ids, 1):
        q_rows = by_question[qid]
        question_text = q_rows[0]["question"]

        ckpt_path = args.checkpoint_dir / f"{qid}.json"
        ratings = None
        if ckpt_path.exists():
            ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if ckpt.get("model") == MODEL and len(ckpt.get("ratings", [])) == len(q_rows):
                print(f"[{idx}/{len(question_ids)}] Skipping {qid} (already rated)", flush=True)
                ratings = ckpt["ratings"]

        if ratings is None:
            print(f"[{idx}/{len(question_ids)}] Rating {qid} ({len(q_rows)} edges)...", flush=True)
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
            entry = row_by_eid[rating["edge_id"]]
            entry["rater_id"] = MODEL
            entry["biologically_meaningful"] = str(rating["biologically_meaningful"])
            entry["relation_type_correct"] = str(rating["relation_type_correct"])
            entry["notes"] = rating["notes"]

        tmp = args.worksheet.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(args.worksheet)

    manifest = {
        "reviewer_type": "AI",
        "role": "supplementary_edge_quality_rater",
        "provider": "google",
        "model": MODEL,
        "input_file": str(args.worksheet),
        "started_at": now_iso,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "question_count": len(question_ids),
        "status": "complete",
        "notes": "Blinded AI audit of NetMedEx graph edges (biologically_meaningful, relation_type_correct). Supplementary AI rating, not a human expert review.",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. Rated {len(rows)} edges across {len(question_ids)} questions.")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
