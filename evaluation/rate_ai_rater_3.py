#!/usr/bin/env python3
"""
AI Rater 3 evaluation script for NetMedEx formal_v2 benchmark.
Uses Gemini 3.6 Flash evaluation model rules to rate candidate PMIDs blinded to rank/system.
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3.csv"
CHECKPOINT_DIR = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_checkpoints"
MANIFEST_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_manifest.json"
INSTRUCTIONS_PATH = BASE_DIR / "evaluation" / "formal_v2" / "ai_rater_3_instructions.md"
README_PATH = BASE_DIR / "evaluation" / "formal_v2" / "README.md"

NOTE_PREFIX = "[AI-GENERATED RATING -- Gemini 3.6 Flash. Supplementary multi-model cross-check.]"

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

def load_dataset():
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    return fieldnames, rows

def save_dataset(fieldnames, rows):
    tmp_path = CSV_PATH.with_suffix(".csv.tmp")
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(CSV_PATH)

def validate_rating(row_id, rel, conf, exc_reason, note):
    if rel not in (0, 1, 2):
        raise ValueError(f"[{row_id}] Invalid relevance: {rel}")
    if conf not in (1, 2, 3):
        raise ValueError(f"[{row_id}] Invalid confidence: {conf}")
    if exc_reason not in ALLOWED_EXCLUSIONS:
        raise ValueError(f"[{row_id}] Invalid exclusion reason: {exc_reason}")
    if rel == 0 and not exc_reason:
        raise ValueError(f"[{row_id}] Relevance 0 must have exclusion_reason")
    if rel > 0 and exc_reason != "":
        raise ValueError(f"[{row_id}] Relevance {rel} must have empty exclusion_reason")
    if not note.strip():
        raise ValueError(f"[{row_id}] Reviewer note cannot be empty")

print("Rater 3 script base loaded successfully.")
