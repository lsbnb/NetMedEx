#!/usr/bin/env python3
"""Audit proposed bridge relations against the frozen PMID abstracts before graph build."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evaluation.rate_ai_panel import DEFAULT_MODELS, init_client, parse_json_object
from netmedex.pubtator_parser import PubTatorIO


SYSTEM_PROMPT = """You are an adversarial biomedical evidence auditor. Judge only the supplied
abstracts. A shared entity mention is not a relation. Require explicit direction and polarity for
each proposed hop; correlation, treatment context, biomarker language, reviews without supporting
mechanistic statements, cross-disease extrapolation, and confounded observations are insufficient.
Reject a composition when the mediator has contradictory roles in the supplied context or when a
document semantically reveals both endpoints despite lexical isolation. Return JSON only."""


def compact_abstract(text: str, max_chars: int) -> str:
    """Keep both background and result/conclusion text within a fixed prompt budget."""
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    head = max(1, max_chars // 3)
    tail = max_chars - head - 5
    return f"{text[:head]} ... {text[-tail:]}"


def validate(payload: dict, expected: dict[tuple[str, str], dict[str, set[str]]]) -> list[dict]:
    rows = payload.get("reviews")
    if not isinstance(rows, list):
        raise ValueError("Response lacks reviews array")
    reviewed = {}
    binary = (
        "source_relation_supported",
        "target_relation_supported",
        "signed_composition_valid",
        "endpoint_semantically_isolated",
    )
    for row in rows:
        key = (str(row.get("question_id", "")).strip(), str(row.get("mediator", "")).strip())
        if key not in expected or key in reviewed:
            raise ValueError(f"Unexpected or duplicate review key: {key}")
        normalized = {"question_id": key[0], "mediator": key[1]}
        for field in binary:
            value = row.get(field)
            if value not in (0, 1) or isinstance(value, bool):
                raise ValueError(f"{key}: invalid {field}: {value!r}")
            normalized[field] = value
        for field, side in (
            ("source_supporting_pmids", "source"),
            ("target_supporting_pmids", "target"),
        ):
            pmids = [str(value) for value in row.get(field, [])]
            if not set(pmids) <= expected[key][side]:
                raise ValueError(f"{key}: {field} contains an unsupplied PMID")
            normalized[field] = sorted(set(pmids))
        supplied = expected[key]["source"] | expected[key]["target"]
        contradictions = [str(value) for value in row.get("contradiction_pmids", [])]
        if not set(contradictions) <= supplied:
            raise ValueError(f"{key}: contradiction_pmids contains an unsupplied PMID")
        normalized["contradiction_pmids"] = sorted(set(contradictions))
        normalized["reason"] = str(row.get("reason", "")).strip()
        normalized["passes_evidence_gate"] = int(all(normalized[field] for field in binary))
        reviewed[key] = normalized
    if set(reviewed) != set(expected):
        raise ValueError(f"Missing reviews: {sorted(set(expected) - set(reviewed))}")
    return [reviewed[key] for key in sorted(reviewed)]


def build_records(corpus_batch: Path, query_spec: Path, max_abstract_chars: int) -> tuple[list[dict], dict]:
    spec = json.loads(query_spec.read_text(encoding="utf-8"))["questions"]
    records, expected = [], {}
    for question_dir in sorted((corpus_batch / "questions").iterdir()):
        if not question_dir.is_dir() or question_dir.name not in spec:
            continue
        manifest = json.loads((question_dir / "corpus_manifest.json").read_text(encoding="utf-8"))
        collection = PubTatorIO.parse(question_dir / "corpus.pubtator")
        articles = {str(article.pmid): article for article in collection.articles}
        mediator_spec = {row["name"]: row for row in spec[question_dir.name]["mediators"]}
        for audit in manifest.get("mediator_audit", []):
            if not audit.get("bridge_eligible"):
                continue
            name = audit["name"]
            if name not in mediator_spec:
                continue
            source = {str(pmid) for pmid in audit["accepted_pmids"]["source"]}
            target = {str(pmid) for pmid in audit["accepted_pmids"]["target"]}
            key = (question_dir.name, name)
            expected[key] = {"source": source, "target": target}
            evidence = {}
            for side, pmids in (("source", source), ("target", target)):
                evidence[side] = [
                    {
                        "pmid": pmid,
                        "title": articles[pmid].title,
                        "abstract": compact_abstract(
                            articles[pmid].abstract or "", max_abstract_chars
                        ),
                    }
                    for pmid in sorted(pmids)
                    if pmid in articles
                ]
            proposal = mediator_spec[name]
            records.append(
                {
                    "question_id": question_dir.name,
                    "mediator": name,
                    "relation_1": proposal.get("relation_1", ""),
                    "relation_2": proposal.get("relation_2", ""),
                    "source_evidence": evidence["source"],
                    "target_evidence": evidence["target"],
                }
            )
    return records, expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-batch", type=Path, required=True)
    parser.add_argument("--query-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--max-abstract-chars", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records, expected = build_records(args.corpus_batch, args.query_spec, args.max_abstract_chars)
    prompt = """Return exactly:
{"reviews":[{"question_id":"...","mediator":"...","source_relation_supported":0,
"target_relation_supported":0,"signed_composition_valid":0,
"endpoint_semantically_isolated":0,"source_supporting_pmids":[],
"target_supporting_pmids":[],"contradiction_pmids":[],"reason":"<=60 words"}]}.
Audit every candidate. Cite only supplied PMIDs. Candidates:
""" + json.dumps(records, ensure_ascii=False)
    print(f"Token budget estimate: {len(records)} candidates, ~{round((len(SYSTEM_PROMPT) + len(prompt)) / 4)} input tokens.")
    if args.dry_run:
        return

    load_dotenv(".env", override=True)
    model = args.model or DEFAULT_MODELS[args.provider]
    client = init_client(args.provider, model)
    raw = client.chat_completion_text(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=4000,
        timeout=600,
        response_format={"type": "json_object"} if args.provider != "anthropic" else None,
    )
    try:
        reviews = validate(parse_json_object(raw), expected)
    except Exception as exc:
        invalid = args.output.with_suffix(args.output.suffix + ".invalid.json")
        invalid.parent.mkdir(parents=True, exist_ok=True)
        invalid.write_text(json.dumps({"validation_error": str(exc), "usage": dict(getattr(client, "last_completion_usage", {}) or {}), "raw_response": raw}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError(f"Invalid evidence review saved to {invalid}: {exc}") from exc

    questions = {}
    for row in reviews:
        questions.setdefault(row["question_id"], {})[row["mediator"]] = {
            key: value for key, value in row.items() if key not in {"question_id", "mediator"}
        }
    artifact = {
        "provider": args.provider,
        "model": model,
        "reviewer_type": "AI PMID-level signed-hop evidence auditor",
        "human_expert_review_claimed": False,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "corpus_freeze_sha256": hashlib.sha256((args.corpus_batch / "freeze.json").read_bytes()).hexdigest(),
        "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
        "questions": questions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"usage": artifact["usage"], "candidate_count": len(reviews), "passed": sum(row["passes_evidence_gate"] for row in reviews)}, indent=2))


if __name__ == "__main__":
    main()
