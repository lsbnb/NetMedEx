#!/usr/bin/env python3
"""Add endpoint-only distractor queries to canonical controlled bridges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_distractor_spec(
    base_spec: dict, preflight: dict, distractor_queries: dict, max_per_side: int
) -> dict:
    eligible_by_question = {
        row["question_id"]: {
            mediator["mediator"]
            for mediator in row.get("mediators", [])
            if mediator.get("bridge_eligible")
        }
        for row in preflight.get("questions", [])
    }
    questions = {}
    for question_id, queries in distractor_queries.items():
        base_question = base_spec.get("questions", {}).get(question_id)
        if base_question is None:
            raise ValueError(f"Question missing from base spec: {question_id}")
        eligible_names = eligible_by_question.get(question_id, set())
        mediators = [
            dict(mediator)
            for mediator in base_question.get("mediators", [])
            if mediator.get("name") in eligible_names
        ]
        if not mediators:
            continue
        question = dict(base_question)
        question["mediators"] = mediators
        question["max_distractors_per_side"] = max_per_side
        question["source_distractor_query"] = queries["source_distractor_query"]
        question["target_distractor_query"] = queries["target_distractor_query"]
        questions[question_id] = question
    return {
        "name": "netmedex-controlled-bridge-reviewed-distractors-v1",
        "selection_rule": "canonical bridge from preflight plus endpoint-only distractors",
        "questions": questions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-spec", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--distractor-queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-per-side", type=int, default=10)
    args = parser.parse_args()
    payload = build_distractor_spec(
        json.loads(args.base_spec.read_text(encoding="utf-8")),
        json.loads(args.preflight.read_text(encoding="utf-8")),
        json.loads(args.distractor_queries.read_text(encoding="utf-8")),
        args.max_per_side,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "question_count": len(payload["questions"]),
                "mediator_count": sum(
                    len(question["mediators"])
                    for question in payload["questions"].values()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
