#!/usr/bin/env python3
"""Use an independent LLM to draft provisional path-qrels labels.

The output is explicitly AI-assisted and is not a human-gold benchmark qrels file. Every decision
is accompanied by a rationale and model metadata so a reviewer can accept, edit, or reject it.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from webapp.llm import ANTHROPIC_BASE_URL, LLMClient

SYSTEM = """You are an independent biomedical evidence adjudicator. Draft provisional labels for candidate paths.
Use only the supplied frozen-corpus excerpts. relevance must be an integer: 2=directly supported complete path,
1=partially supported or one-hop-only/weak evidence, 0=not supported by the supplied evidence. Set
is_negative_control to 1 only when the evidence directly contradicts or clearly lacks the proposed relation;
otherwise 0. bridge_valid and direction_verified are 1 only when supported, else 0. Do not invent PMIDs or claims.
Return JSON only as an array of objects with keys: path_id, relevance, is_negative_control, evidence_level_1,
evidence_level_2, bridge_valid, direction_verified, rationale.
"""


def parse_json(text: str) -> list[dict[str, object]]:
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError(f"LLM did not return a JSON array: {text[:300]}")
    value = json.loads(match.group(0))
    if not isinstance(value, list):
        raise ValueError("LLM JSON result is not an array")
    return value


def corpus_evidence(corpus_path: Path, pmids: str) -> str:
    wanted = {p.strip() for p in pmids.split(";") if p.strip()}
    if not wanted or not corpus_path.exists():
        return ""
    chunks: dict[str, list[str]] = {}
    for line in corpus_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split("|", 2)
        if len(parts) >= 3 and parts[0] in wanted and parts[1] in {"t", "a"}:
            chunks.setdefault(parts[0], []).append(parts[2])
    return "\n".join(f"PMID {pmid}: {' '.join(chunks.get(pmid, []))[:900]}" for pmid in sorted(wanted))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--provider", default="anthropic", choices=["anthropic"])
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    load_dotenv(".env", override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    rows = list(csv.DictReader(args.worksheet.open(newline="", encoding="utf-8")))
    client = LLMClient()
    client.initialize_client(provider="anthropic", api_key=api_key, base_url=ANTHROPIC_BASE_URL, model=args.model)
    decisions: list[dict[str, object]] = []
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        records = []
        for row in batch:
            evidence = corpus_evidence(args.corpus_dir / row["question_id"] / "corpus.pubtator", row["pmids"])
            records.append({"candidate": {k: row.get(k, "") for k in ("path_id", "question_id", "source", "bridge", "target", "relation_1", "relation_2", "direction_1", "direction_2", "pmids", "path_type")}, "evidence": evidence})
        raw = client.chat_completion_text(
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(records, ensure_ascii=False)}],
            temperature=0.0, max_tokens=5000, timeout=600,
        )
        batch_decisions = parse_json(raw)
        expected = {row["path_id"] for row in batch}
        if {str(d.get("path_id")) for d in batch_decisions} != expected:
            raise ValueError(f"Batch path_id mismatch at offset {start}")
        decisions.extend(batch_decisions)
        print(f"adjudicated {min(start + args.batch_size, len(rows))}/{len(rows)}", flush=True)

    by_id = {str(d["path_id"]): d for d in decisions}
    output_rows = []
    for row in rows:
        decision = by_id[row["path_id"]]
        merged = dict(row)
        for key in ("relevance", "is_negative_control", "evidence_level_1", "evidence_level_2", "bridge_valid", "direction_verified"):
            merged[key] = str(decision.get(key, ""))
        merged["notes"] = "AI-assisted provisional label; human review required. " + str(decision.get("rationale", ""))
        output_rows.append(merged)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(output_rows)
    audit = {"provider": args.provider, "model": args.model, "reviewer_type": "AI-assisted provisional path adjudicator", "human_expert_review_claimed": False, "created_at": datetime.now(timezone.utc).isoformat(), "input_rows": len(rows), "decisions": decisions, "usage": dict(getattr(client, "completion_usage_totals", {}) or {})}
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
