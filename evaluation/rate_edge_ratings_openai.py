#!/usr/bin/env python3
"""Blind-rate edge_ratings_worksheet.csv via OpenAI, as a second independent AI rater.

Mirrors rate_edge_ratings_gemini.py's rubric but calls OpenAI gpt-5.6-sol via chat.completions,
matching adjudicate_ai_disagreements.py's call pattern. Operates on its own worksheet copy so it
never overwrites the Gemini rater's completed pass.
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

DEFAULT_WORKSHEET = Path("evaluation/formal/edge_ratings_worksheet_openai.csv")
DEFAULT_MANIFEST = Path("evaluation/formal/edge_rating_manifest_openai.json")
MODEL = "gpt-5.6-sol"

PREFIX = "[AI-GENERATED RATING -- GPT-5.6-sol. Blinded graph-edge quality pass, not a human expert review.]"

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


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def rate_question(client: OpenAI, question: str, rows: list[dict[str, str]]) -> list[dict]:
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

    expected_ids = {row["edge_id"] for row in rows}
    by_id: dict[str, dict] = {}
    for item in items:
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
    row_by_eid = {row["edge_id"]: row for row in rows}
    question_ids = sorted(by_question.keys())
    started_at = datetime.now(timezone.utc).isoformat()

    for idx, qid in enumerate(question_ids, 1):
        q_rows = by_question[qid]
        print(f"[{idx}/{len(question_ids)}] Rating {qid} ({len(q_rows)} edges) via {MODEL}...", flush=True)
        ratings = rate_question(client, q_rows[0]["question"], q_rows)
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
        "provider": "openai",
        "model": MODEL,
        "input_file": str(args.worksheet),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "question_count": len(question_ids),
        "status": "complete",
        "notes": "Second, independent blinded AI rater for NetMedEx graph-edge quality (cross-check against the Gemini 3.1 Pro pass). Supplementary AI rating, not a human expert review.",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. Rated {len(rows)} edges across {len(question_ids)} questions.")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
