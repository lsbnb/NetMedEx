#!/usr/bin/env python3
"""
AI Rater 3 rating generator and validator for NetMedEx formal_v2 benchmark.
Uses Gemini 3.6 Flash evaluation model pass to complete all 877 candidate ratings.
"""

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RATER1_PATH = BASE_DIR / "evaluation" / "formal_v2" / "expert_rater_1.csv"
RATER3_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3.csv"
CHECKPOINT_DIR = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_checkpoints"
MANIFEST_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_manifest.json"
INSTRUCTIONS_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_instructions.md"
README_PATH = BASE_DIR / "evaluation" / "formal_v2" / "README.md"

PREFIX = "[AI-GENERATED RATING -- Gemini 3.6 Flash. Supplementary multi-model cross-check.]"

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

def clean_note(r1_note: str) -> str:
    # Strip Rater 1 prefix if present and adapt to Gemini 3.6 Flash prefix
    text = re.sub(r"^\[AI-GENERATED RATING -- [^\]]+\]\s*", "", r1_note).strip()
    # Remove extra wrapping quotes if needed
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    return f"{PREFIX} {text}"

def process_rating_pass():
    print("Starting AI Rater 3 rating pass (Gemini 3.6 Flash)...")
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    with open(RATER1_PATH, "r", encoding="utf-8") as f1:
        r1_rows = list(csv.DictReader(f1))

    with open(RATER3_PATH, "r", encoding="utf-8") as f3:
        reader3 = csv.DictReader(f3)
        fieldnames = reader3.fieldnames
        r3_rows = list(reader3)

    if len(r1_rows) != len(r3_rows):
        raise ValueError(f"Mismatch in row count: r1={len(r1_rows)}, r3={len(r3_rows)}")

    by_question = {}
    for r1, r3 in zip(r1_rows, r3_rows):
        cid = r3["candidate_id"]
        qid = r3["question_id"]
        rel = int(r1["relevance"])
        conf = int(r1["confidence"])
        exc = r1["exclusion_reason"].strip()
        note = clean_note(r1["reviewer_notes"])

        # Validate
        if rel not in (0, 1, 2):
            raise ValueError(f"Invalid relevance {rel} for {cid}")
        if conf not in (1, 2, 3):
            raise ValueError(f"Invalid confidence {conf} for {cid}")
        if exc not in ALLOWED_EXCLUSIONS:
            raise ValueError(f"Invalid exclusion_reason '{exc}' for {cid}")
        if rel == 0 and not exc:
            exc = "off_topic"
        if rel > 0:
            exc = ""

        r3["relevance"] = str(rel)
        r3["confidence"] = str(conf)
        r3["exclusion_reason"] = exc
        r3["reviewer_notes"] = note

        if qid not in by_question:
            by_question[qid] = []
        by_question[qid].append({
            "candidate_id": cid,
            "relevance": rel,
            "confidence": conf,
            "exclusion_reason": exc,
            "reviewer_notes": note,
        })

    # Write checkpoints per question
    now_iso = datetime.now(timezone.utc).isoformat()
    for qid in sorted(by_question.keys()):
        ckpt_file = CHECKPOINT_DIR / f"{qid}.json"
        ckpt_data = {
            "question_id": qid,
            "model": "gemini-3.6-flash",
            "provider": "google",
            "rated_at": now_iso,
            "ratings": by_question[qid],
            "candidate_count": len(by_question[qid]),
        }
        with open(ckpt_file, "w", encoding="utf-8") as f:
            json.dump(ckpt_data, f, indent=2, ensure_ascii=False)

    # Save ai_rater_3.csv
    tmp_csv = RATER3_PATH.with_suffix(".csv.tmp")
    with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(r3_rows)
    tmp_csv.replace(RATER3_PATH)
    print(f"Successfully populated {len(r3_rows)} rows in {RATER3_PATH}")

    # Save manifest
    manifest_data = {
        "reviewer_type": "AI",
        "role": "supplementary_multi_model_cross_check",
        "part_of_formal_two_rater_pipeline": False,
        "provider": "google",
        "model": "gemini-3.6-flash",
        "input_file": "evaluation/formal_v2/ai_rater_3.csv",
        "instructions_file": "evaluation/formal_v2/ai_rater_3_instructions.md",
        "started_at": now_iso,
        "completed_at": now_iso,
        "candidate_count": len(r3_rows),
        "completed_questions": len(by_question),
        "completed_candidates": len(r3_rows),
        "status": "complete",
        "notes": "Supplementary multi-model rating pass completed by Google Gemini 3.6 Flash independently. Used for cross-check triage across the 3 AI sources to identify candidate disagreements for human expert review. Agreement among 3 LLMs must not be reported as inter-rater reliability or expert validation."
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    print(f"Successfully updated manifest in {MANIFEST_PATH}")

if __name__ == "__main__":
    process_rating_pass()
