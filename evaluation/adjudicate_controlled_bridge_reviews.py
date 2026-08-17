#!/usr/bin/env python3
"""Adjudicate only bridge proposals with internally inconsistent AI review fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evaluation.rate_ai_panel import DEFAULT_MODELS, init_client, parse_json_object


SYSTEM_PROMPT = """You are the final independent biomedical benchmark-spec adjudicator. Review
only candidates whose prior reviewer rejected overall despite passing polarity, canonical-entity,
endpoint-isolation, non-obviousness, and utility thresholds. Decide whether each candidate is worth
a cheap PubMed/PubTator preflight, not whether its biomedical claim is proven. Sparse literature is
a reason to reject only when a two-sided corpus is unlikely to exist. Return JSON only."""


def validate(payload: dict, expected: set[tuple[str, str]]) -> list[dict]:
    rows = payload.get("adjudications")
    if not isinstance(rows, list):
        raise ValueError("Response lacks adjudications array")
    by_key = {}
    for row in rows:
        key = (str(row.get("question_id", "")).strip(), str(row.get("mediator", "")).strip())
        if key not in expected or key in by_key:
            raise ValueError(f"Unexpected or duplicate adjudication: {key}")
        decision = row.get("final_accept")
        if decision not in (0, 1):
            raise ValueError(f"{key}: final_accept must be 0 or 1")
        by_key[key] = {
            "question_id": key[0],
            "mediator": key[1],
            "final_accept": decision,
            "reason": str(row.get("reason", "")).strip(),
        }
    if set(by_key) != expected:
        raise ValueError(f"Missing adjudications: {sorted(expected - set(by_key))}")
    return [by_key[key] for key in sorted(by_key)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accepted-spec", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
    review = json.loads(args.review.read_text(encoding="utf-8"))
    proposal_by_key = {
        (question["question_id"], mediator["name"]): (question, mediator)
        for question in proposals["questions"]
        for mediator in question["mediators"]
    }
    disputed = [
        row
        for row in review["reviews"]
        if row["accept"] == 0
        and row["polarity_coherent"] == 1
        and row["canonical_entity_likely"] == 1
        and row["endpoint_isolation_feasible"] == 1
        and row["non_obviousness"] >= 4
        and row["research_utility"] >= 4
    ]
    if not disputed:
        raise ValueError("No internally disputed candidates require adjudication")
    records = []
    expected = set()
    for prior in disputed:
        key = (prior["question_id"], prior["mediator"])
        question, mediator = proposal_by_key[key]
        expected.add(key)
        records.append(
            {
                "question_id": key[0],
                "mediator": key[1],
                "source_patterns": question["source_patterns"],
                "target_patterns": question["target_patterns"],
                "target_side_forbidden_source_patterns": question[
                    "target_side_forbidden_source_patterns"
                ],
                "proposal": mediator,
                "prior_review": prior,
            }
        )
    prompt = """Return exactly {"adjudications":[{"question_id":"...","mediator":"...",
"final_accept":0,"reason":"<=40 words"}]}. Score every item. `final_accept=1` means only
that the candidate merits automated PubMed/PubTator corpus preflight; later evidence gates remain
mandatory. Items:
""" + json.dumps(records, ensure_ascii=False)
    estimated_chars = len(SYSTEM_PROMPT) + len(prompt)
    print(
        f"Token budget estimate: {len(records)} disputed candidates, {estimated_chars} chars, "
        f"~{round(estimated_chars / 4)} input tokens.",
        flush=True,
    )
    if args.dry_run:
        return

    load_dotenv(".env", override=True)
    model = args.model or DEFAULT_MODELS[args.provider]
    client = init_client(args.provider, model)
    raw = client.chat_completion_text(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1800,
        timeout=600,
        response_format={"type": "json_object"}
        if args.provider != "anthropic"
        else None,
    )
    decisions = validate(parse_json_object(raw), expected)
    artifact = {
        "provider": args.provider,
        "model": model,
        "reviewer_type": "AI corpus-spec adjudicator",
        "human_expert_review_claimed": False,
        "adjudicated_at": datetime.now(timezone.utc).isoformat(),
        "proposal_sha256": hashlib.sha256(args.proposals.read_bytes()).hexdigest(),
        "review_sha256": hashlib.sha256(args.review.read_bytes()).hexdigest(),
        "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
        "adjudications": decisions,
    }
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    accepted_keys = {
        (row["question_id"], row["mediator"])
        for row in decisions
        if row["final_accept"] == 1
    }
    accepted_questions = {}
    for question in proposals["questions"]:
        accepted = [
            mediator
            for mediator in question["mediators"]
            if (question["question_id"], mediator["name"]) in accepted_keys
        ]
        if accepted:
            accepted_questions[question["question_id"]] = {
                "source_patterns": question["source_patterns"],
                "target_patterns": question["target_patterns"],
                "target_side_forbidden_source_patterns": question[
                    "target_side_forbidden_source_patterns"
                ],
                "max_candidates_per_query": 30,
                "max_articles_per_side": 3,
                "mediators": accepted,
            }
    spec = {
        "name": "netmedex-controlled-bridge-ai-adjudicated-v1",
        "proposal_provider": proposals.get("provider"),
        "review_provider": review.get("provider"),
        "adjudication_provider": args.provider,
        "questions": accepted_questions,
    }
    args.accepted_spec.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "usage": artifact["usage"],
                "disputed": len(decisions),
                "accepted": len(accepted_keys),
                "questions": len(accepted_questions),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
