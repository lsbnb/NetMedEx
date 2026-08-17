#!/usr/bin/env python3
"""Resolve pooled-qrels disagreements with AI majority and blinded tie review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


TIE_SYSTEM_PROMPT = """You are the final internal-AI adjudicator for biomedical retrieval relevance.
Read each question, article title, and abstract independently. Assign:
2 = directly addresses the requested relationship, mechanism, intervention, context, or study type;
1 = useful adjacent evidence, review context, a different but informative model, or one segment of
a multi-hop mechanism;
0 = off-topic, wrong entity/context/study type, too broad, or unsupported keyword overlap.
For negative-control questions, use 2 only when the exact direct link is tested. Do not infer
direct evidence from biological plausibility. You are not shown system provenance, ranks, prior
labels, or reviewer identities."""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def load_by_id(path: Path) -> dict[str, dict[str, str]]:
    _fields, rows = read_csv(path)
    result = {row["candidate_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate candidate IDs in {path}")
    if any(row.get("relevance") not in {"0", "1", "2"} for row in rows):
        raise ValueError(f"Incomplete or invalid relevance labels in {path}")
    return result


def adjudicate_ties(
    client: OpenAI, model: str, candidates: list[dict[str, str]]
) -> dict[str, dict[str, Any]]:
    records = [
        {
            "candidate_id": row["candidate_id"],
            "question": row["question"],
            "pmid": row["pmid"],
            "title": row["title"],
            "abstract": row["abstract"] or "[No abstract available]",
        }
        for row in candidates
    ]
    user_prompt = (
        "Independently adjudicate every candidate. Return a JSON object with key `adjudications`, "
        "containing exactly one object per candidate with `candidate_id`, integer `relevance` "
        "(0, 1, or 2), integer `confidence` (1, 2, or 3), and concise `rationale`.\n\n"
        f"Candidates:\n{json.dumps(records, ensure_ascii=False)}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TIE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1,
        max_completion_tokens=8000,
        response_format={"type": "json_object"},
        timeout=600,
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        raise ValueError("Tie adjudicator returned an empty response")
    payload = json.loads(content)
    items = payload.get("adjudications")
    if not isinstance(items, list):
        raise ValueError("Tie adjudicator response lacks an adjudications array")
    expected = {row["candidate_id"] for row in candidates}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        candidate_id = str(item.get("candidate_id", ""))
        relevance = item.get("relevance")
        confidence = item.get("confidence")
        if candidate_id in result or relevance not in {0, 1, 2} or confidence not in {
            1,
            2,
            3,
        }:
            raise ValueError(f"Invalid tie adjudication: {item}")
        result[candidate_id] = {
            "relevance": str(relevance),
            "confidence": confidence,
            "rationale": str(item.get("rationale", "")).strip(),
        }
    if set(result) != expected:
        raise ValueError(
            f"Tie candidate mismatch: missing={sorted(expected - set(result))}, "
            f"extra={sorted(set(result) - expected)}"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir", type=Path, default=Path("evaluation/formal_v2")
    )
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args()

    rater_1 = load_by_id(args.input_dir / "expert_rater_1.csv")
    rater_2 = load_by_id(args.input_dir / "expert_rater_2.csv")
    rater_3 = load_by_id(args.input_dir / "ai_rater_3.csv")
    if set(rater_1) != set(rater_2) or set(rater_1) != set(rater_3):
        raise ValueError("The three rating files do not contain identical candidate IDs")

    fields, adjudication_rows = read_csv(args.input_dir / "adjudication.csv")
    adjudication_by_id = {row["candidate_id"]: row for row in adjudication_rows}
    tie_candidates = []
    majority_count = 0
    for candidate_id in sorted(rater_1):
        labels = [
            rater_1[candidate_id]["relevance"],
            rater_2[candidate_id]["relevance"],
            rater_3[candidate_id]["relevance"],
        ]
        counts = Counter(labels)
        majority = counts.most_common(1)[0]
        row = adjudication_by_id[candidate_id]
        if majority[1] >= 2:
            row["adjudicated_relevance"] = majority[0]
            row["adjudicator_id"] = "internal-ai-majority-r1-r2-r3"
            row["adjudication_notes"] = (
                f"AI majority vote r1/r2/r3={labels[0]}/{labels[1]}/{labels[2]}."
            )
            majority_count += 1
        else:
            tie_candidates.append(rater_2[candidate_id])

    tie_results: dict[str, dict[str, Any]] = {}
    if tie_candidates:
        load_dotenv(override=True)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")
        tie_results = adjudicate_ties(OpenAI(api_key=api_key), args.model, tie_candidates)
        for candidate_id, result in tie_results.items():
            row = adjudication_by_id[candidate_id]
            labels = [
                rater_1[candidate_id]["relevance"],
                rater_2[candidate_id]["relevance"],
                rater_3[candidate_id]["relevance"],
            ]
            row["adjudicated_relevance"] = result["relevance"]
            row["adjudicator_id"] = f"internal-ai-tie-adjudicator:{args.model}"
            row["adjudication_notes"] = (
                f"Three-way AI tie r1/r2/r3={labels[0]}/{labels[1]}/{labels[2]}; "
                f"independent {args.model} decision, confidence={result['confidence']}: "
                f"{result['rationale']}"
            )

    atomic_write_csv(args.input_dir / "adjudication.csv", fields, adjudication_rows)
    log_rows = []
    for row in adjudication_rows:
        candidate_id = row["candidate_id"]
        log_rows.append(
            {
                "candidate_id": candidate_id,
                "question_id": row["question_id"],
                "pmid": row["pmid"],
                "rater_1_relevance": rater_1[candidate_id]["relevance"],
                "rater_2_relevance": rater_2[candidate_id]["relevance"],
                "rater_3_relevance": rater_3[candidate_id]["relevance"],
                "final_relevance": row["adjudicated_relevance"],
                "method": row["adjudicator_id"],
                "notes": row["adjudication_notes"],
            }
        )
    atomic_write_csv(
        args.input_dir / "ai_adjudication_log.csv",
        [
            "candidate_id",
            "question_id",
            "pmid",
            "rater_1_relevance",
            "rater_2_relevance",
            "rater_3_relevance",
            "final_relevance",
            "method",
            "notes",
        ],
        log_rows,
    )
    manifest = {
        "benchmark_version": "formal-v2-internal-ai-adjudicated",
        "status": "complete",
        "candidate_count": len(adjudication_rows),
        "majority_adjudicated_count": majority_count,
        "three_way_tie_count": len(tie_candidates),
        "tie_adjudicator_provider": "openai" if tie_candidates else None,
        "tie_adjudicator_model": args.model if tie_candidates else None,
        "human_expert_review_claimed": False,
        "rubric_sha256": hashlib.sha256(TIE_SYSTEM_PROMPT.encode()).hexdigest(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.input_dir / "ai_adjudication_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
