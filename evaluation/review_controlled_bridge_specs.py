#!/usr/bin/env python3
"""Independently review AI-proposed controlled bridge corpus specifications."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evaluation.rate_ai_panel import DEFAULT_MODELS, init_client, parse_json_object


SYSTEM_PROMPT = """You are an independent biomedical benchmark-design auditor. Review proposed
mediators only as corpus-construction candidates; do not treat them as established answers. Reject
a mediator if its source-to-mediator and mediator-to-target relations have incoherent causal
polarity, it is a synonym/near-restatement of an endpoint, PubTator is unlikely to normalize it to
one shared canonical entity, or target-side endpoint isolation makes the proposed literature query
infeasible. Penalize generic, obvious bridges. Return JSON only. Do not repair a proposal by
inventing a different mediator or query."""

HIDDEN_SYSTEM_PROMPT = """You are an independent adversarial auditor for a Hybrid-RAG hidden
biomedical meaning benchmark. Reject a proposal if it is a textbook or easily inferred mediator,
if either signed relation is vague or non-composable, if one canonical PubTator entity is unlikely
to join both documents, or if Text-RAG could state the same bridge from common biomedical priors.
Accept only candidates likely to add answer-semantic content, not merely a missing PMID or improved
provenance. Do not repair candidates or assume the proposed evidence exists. Return JSON only."""


FIELDS = {
    "accept": (0, 1),
    "polarity_coherent": (0, 1),
    "canonical_entity_likely": (0, 1),
    "endpoint_isolation_feasible": (0, 1),
    "non_obviousness": (1, 5),
    "research_utility": (1, 5),
}

HIDDEN_FIELDS = {
    "signed_composition_valid": (0, 1),
    "answer_incremental_likely": (0, 1),
    "textbook_mediator": (0, 1),
}


def validate(
    payload: dict, expected: set[tuple[str, str]], *, strict_hidden: bool = False
) -> list[dict]:
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("Response lacks reviews array")
    by_key = {}
    for row in reviews:
        key = (str(row.get("question_id", "")).strip(), str(row.get("mediator", "")).strip())
        if key not in expected or key in by_key:
            raise ValueError(f"Unexpected or duplicate review key: {key}")
        normalized = {"question_id": key[0], "mediator": key[1]}
        fields = {**FIELDS, **(HIDDEN_FIELDS if strict_hidden else {})}
        for field, (minimum, maximum) in fields.items():
            value = row.get(field)
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"{key}: invalid {field}: {value!r}")
            normalized[field] = value
        normalized["reason"] = str(row.get("reason", "")).strip()
        normalized["passes_consensus_gate"] = int(
            normalized["accept"] == 1
            and normalized["polarity_coherent"] == 1
            and normalized["canonical_entity_likely"] == 1
            and normalized["endpoint_isolation_feasible"] == 1
            and normalized["non_obviousness"] >= 4
            and normalized["research_utility"] >= 4
            and (
                not strict_hidden
                or (
                    normalized["signed_composition_valid"] == 1
                    and normalized["answer_incremental_likely"] == 1
                    and normalized["textbook_mediator"] == 0
                )
            )
        )
        by_key[key] = normalized
    if set(by_key) != expected:
        raise ValueError(f"Missing reviews: {sorted(expected - set(by_key))}")
    return [by_key[key] for key in sorted(by_key)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accepted-spec", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--hidden-mode",
        action="store_true",
        help="Require answer incrementality and reject textbook mediators.",
    )
    args = parser.parse_args()

    proposal_artifact = json.loads(args.proposals.read_text(encoding="utf-8"))
    proposal_questions = proposal_artifact["questions"]
    records = []
    expected = set()
    for question in proposal_questions:
        for mediator in question["mediators"]:
            key = (question["question_id"], mediator["name"])
            expected.add(key)
            records.append(
                {
                    "question_id": question["question_id"],
                    "source_patterns": question["source_patterns"],
                    "target_patterns": question["target_patterns"],
                    "target_side_forbidden_source_patterns": question[
                        "target_side_forbidden_source_patterns"
                    ],
                    **mediator,
                }
            )
    if args.hidden_mode:
        prompt = """Return exactly:
{"reviews":[{"question_id":"...","mediator":"...","accept":0,
"polarity_coherent":0,"canonical_entity_likely":0,"endpoint_isolation_feasible":0,
"signed_composition_valid":0,"answer_incremental_likely":0,"textbook_mediator":1,
"non_obviousness":1,"research_utility":1,"reason":"<=35 words"}]}.
Score every item. The downstream gate requires accept=1, all positive binary fields=1,
textbook_mediator=0, non_obviousness>=4, and research_utility>=4.
`non_obviousness` and `research_utility` MUST each be exactly one of 1, 2, 3, 4, or 5;
never output 0 or a number greater than 5. Proposals:
""" + json.dumps(records, ensure_ascii=False)
        system_prompt = HIDDEN_SYSTEM_PROMPT
    else:
        prompt = """Return exactly:
{"reviews":[{"question_id":"...","mediator":"...","accept":0,
"polarity_coherent":0,"canonical_entity_likely":0,"endpoint_isolation_feasible":0,
"non_obviousness":1,"research_utility":1,"reason":"<=30 words"}]}.
Score every supplied item. `accept` is your overall technical judgment, but the downstream gate
also requires every binary field=1 and both ordinal fields>=4. Proposals:
""" + json.dumps(records, ensure_ascii=False)
        system_prompt = SYSTEM_PROMPT
    estimated_chars = len(system_prompt) + len(prompt)
    print(
        f"Token budget estimate: {len(records)} candidates, {estimated_chars} prompt chars, "
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=8000,
        timeout=600,
        response_format={"type": "json_object"}
        if args.provider != "anthropic"
        else None,
    )
    try:
        reviews = validate(
            parse_json_object(raw), expected, strict_hidden=args.hidden_mode
        )
    except Exception as exc:
        invalid_path = args.output.with_suffix(args.output.suffix + ".invalid.json")
        invalid_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_path.write_text(
            json.dumps(
                {
                    "provider": args.provider,
                    "model": model,
                    "review_strategy": (
                        "hidden_semantic" if args.hidden_mode else "standard"
                    ),
                    "validation_error": str(exc),
                    "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
                    "raw_response": raw,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise ValueError(
            f"Invalid review response saved to {invalid_path}: {exc}"
        ) from exc
    artifact = {
        "provider": args.provider,
        "model": model,
        "reviewer_type": "AI corpus-spec reviewer",
        "human_expert_review_claimed": False,
        "review_strategy": "hidden_semantic" if args.hidden_mode else "standard",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "proposal_sha256": hashlib.sha256(args.proposals.read_bytes()).hexdigest(),
        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
        "reviews": reviews,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    review_by_key = {(row["question_id"], row["mediator"]): row for row in reviews}
    accepted_questions = {}
    for question in proposal_questions:
        accepted = [
            mediator
            for mediator in question["mediators"]
            if review_by_key[(question["question_id"], mediator["name"])][
                "passes_consensus_gate"
            ]
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
    accepted_spec = {
        "name": "netmedex-controlled-bridge-ai-consensus-v1",
        "proposal_provider": proposal_artifact.get("provider"),
        "review_provider": args.provider,
        "questions": accepted_questions,
    }
    args.accepted_spec.write_text(
        json.dumps(accepted_spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "usage": artifact["usage"],
                "candidate_count": len(reviews),
                "accepted_candidate_count": sum(
                    row["passes_consensus_gate"] for row in reviews
                ),
                "accepted_question_count": len(accepted_questions),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
