#!/usr/bin/env python3
"""
Live Gemini Pro API rating pipeline for AI Rater 3 (formal_v2 benchmark).
Calls Google Gemini Pro API (gemini-3.1-pro-preview) for all 50 questions / 877 candidate items.
Supports checkpoint resumption and ultra-robust JSON parsing.
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3.csv"
CHECKPOINT_DIR = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_checkpoints"
MANIFEST_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_manifest.json"
INSTRUCTIONS_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_instructions.md"
README_PATH = BASE_DIR / "evaluation" / "formal_v2" / "README.md"

PREFIX = "[AI-GENERATED RATING -- Gemini 3.1 Pro. Supplementary multi-model cross-check.]"

SYSTEM_PROMPT = """You are a biomedical information-retrieval relevance assessor.
Judge each PubMed article only against the supplied question based on title and abstract. You are blinded to retrieval system, rank, score, and prior labels.

Relevance labels:
2 = directly addresses the requested entity relationship, mechanism, intervention, disease context, population, or study type.
1 = useful adjacent evidence, review-level context, a different but informative model, or one supported segment of a multi-hop mechanism.
0 = off-topic, wrong entity/context/study type, too broad, or keyword overlap without support.

For negative-control questions asking whether direct evidence exists, assign 2 only if the exact direct causal or mechanistic link is tested. Biological plausibility alone is not direct evidence.

Confidence:
3 = clear from title/abstract; 2 = some ambiguity; 1 = full text or specialist adjudication needed.

For relevance 0, exclusion_reason must be exactly one of: off_topic, wrong_entity, wrong_context, wrong_study_type, too_broad, no_usable_evidence, duplicate, other. For relevance 1 or 2, use an empty exclusion_reason "". Return concise reviewer_notes grounded in the supplied record. Do not use outside knowledge to invent evidence."""

ALLOWED_EXCLUSIONS = {
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

def parse_json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # Attempt 1: Extract first outer JSON object {...}
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        blob = match.group(1).strip()
        try:
            return json.loads(blob)
        except Exception:
            # Clean trailing commas inside JSON
            cleaned = re.sub(r",\s*([\]}])", r"\1", blob)
            try:
                return json.loads(cleaned)
            except Exception:
                pass

    # Attempt 2: Regex extraction of individual rating objects
    items = []
    pattern = r'\{\s*"candidate_id"\s*:\s*"([^"]+)"\s*,\s*"relevance"\s*:\s*(\d+)\s*,\s*"confidence"\s*:\s*(\d+)\s*,\s*"exclusion_reason"\s*:\s*"([^"]*)"\s*,\s*"reviewer_notes"\s*:\s*"([^"]*)"\s*\}'
    for m in re.finditer(pattern, text):
        items.append({
            "candidate_id": m.group(1),
            "relevance": int(m.group(2)),
            "confidence": int(m.group(3)),
            "exclusion_reason": m.group(4),
            "reviewer_notes": m.group(5),
        })
    if items:
        return {"ratings": items}

    raise ValueError("Could not parse valid ratings JSON object from model response")

def validate_ratings(payload, expected_ids):
    ratings = payload.get("ratings")
    if not isinstance(ratings, list):
        raise ValueError("Response does not contain a ratings array")

    by_id = {}
    for item in ratings:
        cid = str(item.get("candidate_id", "")).strip()
        rel = item.get("relevance")
        conf = item.get("confidence")
        reason = str(item.get("exclusion_reason", "")).strip()
        note = str(item.get("reviewer_notes", "")).strip()

        if cid in by_id:
            raise ValueError(f"Duplicate candidate_id: {cid}")
        if rel not in {0, 1, 2}:
            raise ValueError(f"[{cid}] Invalid relevance: {rel}")
        if conf not in {1, 2, 3}:
            raise ValueError(f"[{cid}] Invalid confidence: {conf}")
        if reason not in ALLOWED_EXCLUSIONS:
            raise ValueError(f"[{cid}] Invalid exclusion_reason: '{reason}'")
        if rel == 0 and not reason:
            reason = "off_topic"
        if rel > 0:
            reason = ""

        if not note.startswith("[AI-GENERATED RATING"):
            note = f"{PREFIX} {note}"

        by_id[cid] = {
            "candidate_id": cid,
            "relevance": rel,
            "confidence": conf,
            "exclusion_reason": reason,
            "reviewer_notes": note,
        }

    if set(by_id.keys()) != expected_ids:
        missing = sorted(expected_ids - set(by_id.keys()))
        extra = sorted(set(by_id.keys()) - expected_ids)
        raise ValueError(f"Candidate ID mismatch. Missing: {missing}, Extra: {extra}")

    return [by_id[cid] for cid in sorted(by_id.keys())]

def rate_question_via_gemini_api(api_key, question, candidates, model="gemini-3.1-pro-preview", retries=5):
    records = [
        {
            "candidate_id": row["candidate_id"],
            "pmid": row["pmid"],
            "title": row["title"],
            "abstract": row["abstract"] or "[No abstract available]",
        }
        for row in candidates
    ]
    user_prompt = (
        f"Question:\n{question}\n\n"
        "Assess every candidate below against the question. Return a JSON object with key `ratings`, "
        "whose value is an array containing exactly one object per candidate. Each object must contain "
        "`candidate_id` (string), `relevance` (integer 0, 1, or 2), `confidence` (integer 1, 2, or 3), "
        "`exclusion_reason` (string, required for relevance 0; empty string for relevance 1 or 2), and "
        "`reviewer_notes` (string, concise rationale starting with '[AI-GENERATED RATING -- Gemini 3.1 Pro. Supplementary multi-model cross-check.]').\n\n"
        f"Candidates:\n{json.dumps(records, ensure_ascii=False)}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code != 200:
                raise ValueError(f"API HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed_json = parse_json_from_text(raw_text)
            expected_ids = {c["candidate_id"] for c in candidates}
            validated_ratings = validate_ratings(parsed_json, expected_ids)
            return validated_ratings, raw_text
        except Exception as exc:
            last_err = exc
            print(f"  Attempt {attempt} failed: {exc}. Retrying...")
            time.sleep(3 * attempt)

    raise RuntimeError(f"Failed to rate question after {retries} attempts: {last_err}")

def main():
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your-gemini-key"):
        raise ValueError("Valid GEMINI_API_KEY not found in environment or .env")

    model = "gemini-3.1-pro-preview"
    print(f"Starting Live Gemini Pro API Rating pass using model '{model}'...")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    by_question = {}
    for r in rows:
        qid = r["question_id"]
        if qid not in by_question:
            by_question[qid] = []
        by_question[qid].append(r)

    question_ids = sorted(by_question.keys())
    total_q = len(question_ids)

    row_by_id = {r["candidate_id"]: r for r in rows}
    now_iso = datetime.now(timezone.utc).isoformat()

    completed_candidates = 0
    for idx, qid in enumerate(question_ids, 1):
        candidates = by_question[qid]
        q_text = candidates[0]["question"]

        ckpt_path = CHECKPOINT_DIR / f"{qid}.json"
        if ckpt_path.exists():
            try:
                ckpt_data = json.loads(ckpt_path.read_text(encoding="utf-8"))
                if ckpt_data.get("model") == model and len(ckpt_data.get("ratings", [])) == len(candidates):
                    print(f"[{idx}/{total_q}] Skipping {qid} (already rated via {model} in checkpoint)", flush=True)
                    ratings = ckpt_data["ratings"]
                    for rating in ratings:
                        cid = rating["candidate_id"]
                        r_entry = row_by_id[cid]
                        r_entry["relevance"] = str(rating["relevance"])
                        r_entry["confidence"] = str(rating["confidence"])
                        r_entry["exclusion_reason"] = rating["exclusion_reason"]
                        r_entry["reviewer_notes"] = rating["reviewer_notes"]
                    completed_candidates += len(candidates)
                    continue
            except Exception as e:
                print(f"Warning loading checkpoint {ckpt_path}: {e}")

        print(f"[{idx}/{total_q}] Rating {qid} ({len(candidates)} candidates) via {model}...", flush=True)

        ratings, raw_resp = rate_question_via_gemini_api(
            api_key=api_key,
            question=q_text,
            candidates=candidates,
            model=model,
        )

        for rating in ratings:
            cid = rating["candidate_id"]
            r_entry = row_by_id[cid]
            r_entry["relevance"] = str(rating["relevance"])
            r_entry["confidence"] = str(rating["confidence"])
            r_entry["exclusion_reason"] = rating["exclusion_reason"]
            r_entry["reviewer_notes"] = rating["reviewer_notes"]

        # Save checkpoint
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump({
                "question_id": qid,
                "model": model,
                "provider": "google",
                "rated_at": datetime.now(timezone.utc).isoformat(),
                "ratings": ratings,
                "raw_response_sha256": hashlib.sha256(raw_resp.encode()).hexdigest(),
            }, f, indent=2, ensure_ascii=False)

        completed_candidates += len(candidates)

        # Atomically write interim CSV updates
        tmp_csv = CSV_PATH.with_suffix(".csv.tmp")
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tmp_csv.replace(CSV_PATH)

        time.sleep(0.5)

    print(f"\nSuccessfully rated all {len(rows)} candidates via Gemini Pro API!")

    # Summary statistics
    rel_counts = {}
    for r in rows:
        v = r["relevance"]
        rel_counts[v] = rel_counts.get(v, 0) + 1

    print("Live Gemini Pro API Relevance Distribution:", rel_counts)

    # Manifest update
    manifest = {
        "reviewer_type": "AI",
        "role": "supplementary_multi_model_cross_check",
        "part_of_formal_two_rater_pipeline": False,
        "provider": "google",
        "model": model,
        "api_endpoint": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "input_file": "evaluation/formal_v2/ai_rater_3.csv",
        "instructions_file": "evaluation/formal_v2/ai_rater_3_instructions.md",
        "started_at": now_iso,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(rows),
        "completed_questions": total_q,
        "completed_candidates": len(rows),
        "status": "complete",
        "relevance_distribution": rel_counts,
        "notes": f"Live API rating pass completed directly via Google Gemini Pro API ({model}). All 877 candidate items evaluated via structured JSON calls."
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Updated manifest: {MANIFEST_PATH}")

if __name__ == "__main__":
    main()
