#!/usr/bin/env python3
"""Select reviewed mediator proposals into a deterministic corpus-build spec."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def select_questions(
    proposal: dict,
    review: dict,
    *,
    min_non_obviousness: int = 3,
    min_research_utility: int = 4,
    excluded_pairs: set[tuple[str, str]] | None = None,
) -> tuple[dict, list[dict]]:
    """Return corpus-builder questions and an auditable selection table."""
    excluded_pairs = {
        (str(question_id), str(mediator).casefold())
        for question_id, mediator in (excluded_pairs or set())
    }
    review_by_pair = {
        (str(row["question_id"]), str(row["mediator"]).casefold()): row
        for row in review.get("reviews", [])
    }
    selected_questions = {}
    audit = []
    for question in proposal.get("questions", []):
        question_id = str(question["question_id"])
        selected_mediators = []
        for mediator in question.get("mediators", []):
            pair = (question_id, str(mediator["name"]).casefold())
            reviewed = review_by_pair.get(pair)
            reasons = []
            if reviewed is None:
                reasons.append("review_missing")
            else:
                for field in (
                    "polarity_coherent",
                    "canonical_entity_likely",
                    "endpoint_isolation_feasible",
                ):
                    if int(reviewed.get(field, 0) or 0) != 1:
                        reasons.append(f"{field}_failed")
                if int(reviewed.get("non_obviousness", 0) or 0) < min_non_obviousness:
                    reasons.append("non_obviousness_below_threshold")
                if int(reviewed.get("research_utility", 0) or 0) < min_research_utility:
                    reasons.append("research_utility_below_threshold")
            if pair in excluded_pairs:
                reasons.append("previously_tested")
            selected = not reasons
            if selected:
                selected_mediators.append(dict(mediator))
            audit.append(
                {
                    "question_id": question_id,
                    "mediator": mediator["name"],
                    "selected": selected,
                    "reasons": reasons or ["review_thresholds_passed"],
                    "non_obviousness": int(
                        (reviewed or {}).get("non_obviousness", 0) or 0
                    ),
                    "research_utility": int(
                        (reviewed or {}).get("research_utility", 0) or 0
                    ),
                }
            )
        if selected_mediators:
            selected_questions[question_id] = {
                "source_patterns": list(question["source_patterns"]),
                "target_patterns": list(question["target_patterns"]),
                "target_side_forbidden_source_patterns": list(
                    question.get("target_side_forbidden_source_patterns", [])
                ),
                "max_candidates_per_query": 30,
                "max_articles_per_side": 3,
                "mediators": selected_mediators,
            }
    return selected_questions, audit


def select_questions_evidence_first(proposal: dict) -> tuple[dict, list[dict]]:
    """Pass every proposal to PMID-level evidence collection before novelty review."""
    questions = {}
    audit = []
    for question in proposal.get("questions", []):
        question_id = str(question["question_id"])
        mediators = [dict(row) for row in question.get("mediators", [])]
        if not mediators:
            continue
        questions[question_id] = {
            "source_patterns": list(question["source_patterns"]),
            "target_patterns": list(question["target_patterns"]),
            "target_side_forbidden_source_patterns": list(
                question.get("target_side_forbidden_source_patterns", [])
            ),
            "max_candidates_per_query": 30,
            "max_articles_per_side": 3,
            "mediators": mediators,
        }
        audit.extend(
            {
                "question_id": question_id,
                "mediator": mediator["name"],
                "selected": True,
                "reasons": ["pending_pmid_level_evidence_audit"],
            }
            for mediator in mediators
        )
    return questions, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-non-obviousness", type=int, default=3)
    parser.add_argument("--min-research-utility", type=int, default=4)
    parser.add_argument(
        "--evidence-first",
        action="store_true",
        help="Skip proposal plausibility scores and send all candidates to PMID audit.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="QUESTION_ID:MEDIATOR",
        help="Exclude a previously tested question/mediator pair.",
    )
    args = parser.parse_args()
    excluded_pairs = set()
    for value in args.exclude:
        if ":" not in value:
            raise ValueError(f"Invalid --exclude value: {value!r}")
        question_id, mediator = value.split(":", 1)
        excluded_pairs.add((question_id, mediator))

    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    if args.evidence_first:
        if args.review:
            parser.error("--review cannot be combined with --evidence-first")
        if excluded_pairs:
            parser.error("--exclude is not supported with --evidence-first")
        questions, audit = select_questions_evidence_first(proposal)
    else:
        if not args.review:
            parser.error("--review is required unless --evidence-first is used")
        review = json.loads(args.review.read_text(encoding="utf-8"))
        questions, audit = select_questions(
            proposal,
            review,
            min_non_obviousness=args.min_non_obviousness,
            min_research_utility=args.min_research_utility,
            excluded_pairs=excluded_pairs,
        )
    payload = {
        "name": (
            "netmedex-controlled-bridge-evidence-first-v1"
            if args.evidence_first
            else "netmedex-controlled-bridge-reviewed-preflight-v1"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "min_non_obviousness": args.min_non_obviousness,
            "min_research_utility": args.min_research_utility,
            "required_binary_fields": [
                "polarity_coherent",
                "canonical_entity_likely",
                "endpoint_isolation_feasible",
            ],
            "excluded_pairs": sorted(
                [list(pair) for pair in excluded_pairs], key=lambda row: (row[0], row[1])
            ),
            "audit": audit,
            "evidence_first": args.evidence_first,
        },
        "questions": questions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "question_count": len(questions),
                "mediator_count": sum(
                    len(question["mediators"]) for question in questions.values()
                ),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
