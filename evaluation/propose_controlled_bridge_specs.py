#!/usr/bin/env python3
"""Use one AI provider to propose controlled cross-document bridge search specs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evaluation.rate_ai_panel import DEFAULT_MODELS, init_client, parse_json_object


SYSTEM_PROMPT = """You design biomedical retrieval benchmarks, not answers. For each endpoint-only
question, propose at most three mediator entities suitable for a controlled cross-document bridge
corpus. Prefer canonical genes, proteins, chemicals, pathways, or diseases likely to receive the
same PubTator identifier on both sides. A useful mediator supports a polarity-coherent chain from
source to mediator to target, is not merely a synonym of either endpoint, and has plausible
source-mediator and mediator-target literature. Favor non-obvious, research-useful mechanisms over
generic inflammation/fibrosis. The mediator must not appear in the endpoint-only system question.
Return JSON only and do not claim that any proposal is already evidence-validated."""

LATENT_HIDDEN_SYSTEM_PROMPT = """You design adversarial biomedical retrieval benchmarks for
testing whether a knowledge graph reveals non-textbook cross-document meaning that text-only RAG
is unlikely to reconstruct from familiar priors. For each endpoint-only question propose at most
two canonical mediator entities. Exclude every supplied prior mediator and reject generic hubs,
canonical textbook mechanisms, endpoint synonyms, broad processes, and standard-of-care facts.
Each proposal must specify two signed, directionally composable relations supported by separate
literature searches, explain why a text-only top-k answer may miss the composition, and state one
falsifiable research hypothesis enabled by the bridge. Prefer specific genes, proteins, metabolites,
or molecular complexes likely to share one PubTator identifier across both sides. Return JSON only;
these are search candidates, not validated evidence."""


def normalize_pubmed_query_fields(query: str) -> str:
    """Field simple top-level AND clauses without another model call.

    Proposal models commonly emit ``A AND B[Title/Abstract]`` even when instructed
    to field both concepts. Appending the field to an otherwise unfielded top-level
    clause is a syntax-only repair; it does not change the proposed concepts.
    """
    clauses = re.split(r"\s+AND\s+", query.strip(), flags=re.IGNORECASE)
    if len(clauses) < 2:
        return query.strip()
    return " AND ".join(
        clause.strip()
        if "[title/abstract]" in clause.casefold()
        else f"{clause.strip()}[Title/Abstract]"
        for clause in clauses
    )


def validate(
    payload: dict, expected_ids: set[str], *, require_latent_fields: bool = False
) -> dict:
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Response lacks questions array")
    by_id = {}
    for item in questions:
        question_id = str(item.get("question_id", "")).strip()
        if question_id not in expected_ids or question_id in by_id:
            raise ValueError(f"Unexpected or duplicate question_id: {question_id!r}")
        mediators = item.get("mediators")
        maximum = 2 if require_latent_fields else 3
        if not isinstance(mediators, list) or not 1 <= len(mediators) <= maximum:
            raise ValueError(f"{question_id}: expected 1-{maximum} mediators")
        normalized_mediators = []
        seen = set()
        for mediator in mediators:
            name = str(mediator.get("name", "")).strip()
            if not name or name.casefold() in seen:
                raise ValueError(f"{question_id}: blank or duplicate mediator")
            seen.add(name.casefold())
            patterns = mediator.get("patterns")
            if not isinstance(patterns, list) or not patterns:
                raise ValueError(f"{question_id}/{name}: patterns missing")
            for pattern in patterns:
                re.compile(str(pattern), re.IGNORECASE)
            source_query = normalize_pubmed_query_fields(
                str(mediator.get("source_query", ""))
            )
            target_query = normalize_pubmed_query_fields(
                str(mediator.get("target_query", ""))
            )
            if not source_query or not target_query:
                raise ValueError(f"{question_id}/{name}: query missing")
            for side, query in (("source", source_query), ("target", target_query)):
                if query.casefold().count("[title/abstract]") < 2:
                    raise ValueError(
                        f"{question_id}/{name}: {side}_query must field both endpoint "
                        "and mediator terms with [Title/Abstract]"
                    )
            normalized = {
                    "name": name,
                    "patterns": [str(pattern) for pattern in patterns],
                    "source_query": source_query,
                    "target_query": target_query,
                    "rationale": str(mediator.get("rationale", "")).strip(),
                }
            if require_latent_fields:
                for field in (
                    "relation_1",
                    "relation_2",
                    "why_text_rag_may_miss",
                    "falsifiable_hypothesis",
                ):
                    value = str(mediator.get(field, "")).strip()
                    if not value:
                        raise ValueError(f"{question_id}/{name}: {field} missing")
                    normalized[field] = value
            normalized_mediators.append(normalized)
        by_id[question_id] = {
            "question_id": question_id,
            "source_patterns": [str(x) for x in item.get("source_patterns", [])],
            "target_patterns": [str(x) for x in item.get("target_patterns", [])],
            "target_side_forbidden_source_patterns": [
                str(x) for x in item.get("target_side_forbidden_source_patterns", [])
            ],
            "mediators": normalized_mediators,
        }
        for field in (
            "source_patterns",
            "target_patterns",
            "target_side_forbidden_source_patterns",
        ):
            if not by_id[question_id][field]:
                raise ValueError(f"{question_id}: {field} missing")
            for pattern in by_id[question_id][field]:
                re.compile(pattern, re.IGNORECASE)
    if set(by_id) != expected_ids:
        raise ValueError(f"Missing questions: {sorted(expected_ids - set(by_id))}")
    return {"questions": [by_id[qid] for qid in sorted(by_id)]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit proposal generation to selected question IDs.",
    )
    parser.add_argument(
        "--latent-hidden",
        action="store_true",
        help="Require non-textbook signed bridges aimed at answer-semantic incrementality.",
    )
    parser.add_argument(
        "--exclude-proposals",
        action="append",
        type=Path,
        default=[],
        help="Prior proposal artifact whose mediators must not be repeated.",
    )
    args = parser.parse_args()

    with args.queries.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if args.only:
        selected = set(args.only)
        rows = [row for row in rows if row["question_id"] in selected]
        missing = selected - {row["question_id"] for row in rows}
        if missing:
            raise ValueError(f"Unknown --only question IDs: {sorted(missing)}")
    excluded_by_question: dict[str, set[str]] = {}
    for proposal_path in args.exclude_proposals:
        prior = json.loads(proposal_path.read_text(encoding="utf-8"))
        for question in prior.get("questions", []):
            excluded_by_question.setdefault(str(question["question_id"]), set()).update(
                str(mediator["name"]) for mediator in question.get("mediators", [])
            )
    records = [
        {
            "question_id": row["question_id"],
            "domain": row.get("domain", ""),
            "question": row["question"],
            "excluded_mediators": sorted(
                excluded_by_question.get(row["question_id"], set()), key=str.casefold
            ),
        }
        for row in rows
    ]
    expected_ids = {row["question_id"] for row in rows}
    if args.latent_hidden:
        prompt = """Return this exact structure:
{"questions":[{"question_id":"...","source_patterns":["regex"],
"target_patterns":["regex"],"target_side_forbidden_source_patterns":["broader regex"],
"mediators":[{"name":"...","patterns":["regex"],"source_query":"PubMed query",
"target_query":"PubMed query","relation_1":"signed source -> mediator relation",
"relation_2":"signed mediator -> target relation","why_text_rag_may_miss":"<=35 words",
"falsifiable_hypothesis":"<=35 words","rationale":"<=25 words"}]}]}.

Use PubMed [Title/Abstract] syntax. The two queries must retrieve different sides of the bridge;
do not add NOT clauses. Never repeat excluded_mediators. Questions:
""" + json.dumps(records, ensure_ascii=False)
        system_prompt = LATENT_HIDDEN_SYSTEM_PROMPT
    else:
        prompt = """Return this exact structure:
{"questions":[{"question_id":"...","source_patterns":["regex"],
"target_patterns":["regex"],"target_side_forbidden_source_patterns":["broader regex"],
"mediators":[{"name":"...","patterns":["regex"],"source_query":"PubMed query",
"target_query":"PubMed query","rationale":"<=30 words"}]}]}.

Use PubMed [Title/Abstract] syntax in queries. Source queries must seek source+mediator;
target queries must seek mediator+target. Do not add NOT clauses: endpoint isolation is applied
after fetching. Regexes must be valid Python regex strings. Questions:
""" + json.dumps(records, ensure_ascii=False)
        system_prompt = SYSTEM_PROMPT
    estimated_chars = len(system_prompt) + len(prompt)
    print(
        f"Token budget estimate: {estimated_chars} prompt chars, "
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
        max_tokens=9000,
        timeout=600,
        response_format={"type": "json_object"}
        if args.provider != "anthropic"
        else None,
    )
    try:
        proposals = validate(
            parse_json_object(raw), expected_ids, require_latent_fields=args.latent_hidden
        )
    except Exception as exc:
        invalid_path = args.output.with_suffix(args.output.suffix + ".invalid.json")
        invalid_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_path.write_text(
            json.dumps(
                {
                    "provider": args.provider,
                    "model": model,
                    "proposal_strategy": (
                        "latent_hidden" if args.latent_hidden else "standard"
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
            f"Invalid proposal response saved to {invalid_path}: {exc}"
        ) from exc
    artifact = {
        "provider": args.provider,
        "model": model,
        "reviewer_type": "AI corpus-spec proposer",
        "human_expert_review_claimed": False,
        "proposal_strategy": "latent_hidden" if args.latent_hidden else "standard",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashlib.sha256(
            json.dumps(records, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
        **proposals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"usage": artifact["usage"], "questions": len(proposals["questions"])}, indent=2))


if __name__ == "__main__":
    main()
