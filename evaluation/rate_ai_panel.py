#!/usr/bin/env python3
"""Run a resumable, provider-diverse blinded AI panel over edge, hypothesis, or answer worksheets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from webapp.llm import (
    ANTHROPIC_BASE_URL,
    GEMINI_OPENAI_BASE_URL,
    OPENAI_BASE_URL,
    LLMClient,
    gemini_api_disabled,
)

TASK_CONFIG = {
    "edge": {
        "id_field": "edge_id",
        "score_fields": {
            "entity_valid": (0, 1),
            "relation_exists": (0, 1),
            "relation_type_correct": (0, 1),
            "direction_correct": (0, 1),
            "evidence_support": (0, 1),
            "confidence": (1, 3),
        },
    },
    "hypothesis": {
        "id_field": "hypothesis_id",
        "score_fields": {
            "novelty": (1, 5),
            "plausibility": (1, 5),
            "testability": (1, 5),
            "research_value": (1, 5),
        },
    },
    "answer": {
        "id_field": "answer_id",
        "score_fields": {
            "correctness": (1, 5),
            "completeness": (1, 5),
            "relevance": (1, 5),
            "grounding": (1, 5),
            "mechanistic_coherence": (1, 5),
            "research_value": (1, 5),
        },
    },
    "hidden_claim": {
        "id_field": "hidden_claim_id",
        "score_fields": {
            "hybrid_only": (0, 1),
            "path_traceable": (0, 1),
            "evidence_support": (0, 1),
            "relation_direction_correct": (0, 1),
            "multi_document_or_hop": (0, 1),
            "non_obviousness": (1, 5),
            "research_utility": (1, 5),
            "unsupported_novelty": (0, 1),
        },
    },
}

DEFAULT_MODELS = {
    "openai": "gpt-5.6-sol",
    "google": "gemini-3.1-pro-preview",
    "anthropic": "claude-sonnet-4-6",
    "local": "gpt-oss:120b",
}

SYSTEM_PROMPTS = {
    "edge": """You are an independent biomedical knowledge-graph auditor. Judge only from the
provided question, article titles, abstracts, and extraction evidence. Do not repair missing
evidence with outside knowledge. For every edge score: entity_valid, relation_exists,
relation_type_correct, direction_correct, evidence_support (all 0/1), and confidence (1-3).
Direction_correct is 1 for a symmetric relation when the symmetric label is appropriate. A
plausible relation without textual support must receive evidence_support=0. Return JSON only.""",
    "hypothesis": """You are an independent blinded biomedical reviewer. You do not know which
system produced answer A or B. Score novelty, plausibility, testability, and research_value from
1-5. Judge scientific content rather than verbosity. Also choose preferred_item_id as one supplied
ID or 'tie'. Do not infer system identity. Return JSON only.""",
    "answer": """You are an independent blinded biomedical answer reviewer. You do not know which
system produced answer A or B. Score correctness, completeness, relevance, grounding,
mechanistic_coherence, and research_value from 1-5. Penalize unsupported claims, fabricated
citations, direction errors, and failure to distinguish human, animal, and in-vitro evidence.
Also choose preferred_item_id as one supplied ID or 'tie'. Judge content rather than length and
do not infer system identity. Return JSON only.""",
    "hidden_claim": """You are an independent biomedical hidden-information auditor. The candidate
system identity is withheld. Judge only from the candidate claim, frozen path evidence, and the
comparison answer. hybrid_only=1 only when the comparison answer lacks the same or an equivalent
claim. path_traceable=1 only when the supplied path exactly supports the entities and hops.
evidence_support=1 only when every required hop has an explicit supporting quote and PMID.
relation_direction_correct=1 only when every stated relation and direction matches those quotes.
multi_document_or_hop=1 when the claim requires at least two supported hops or integrates distinct
documents. Score non_obviousness and research_utility from 1-5. unsupported_novelty=1 whenever the
claim adds content not justified by the supplied evidence. Do not repair evidence with outside
knowledge. Return JSON only.""",
}


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    decoder = json.JSONDecoder()
    if cleaned.startswith("["):
        try:
            value, _end = decoder.raw_decode(cleaned)
            if isinstance(value, list):
                return {"ratings": value}
        except json.JSONDecodeError:
            pass
    starts = [index for index, char in enumerate(cleaned) if char == "{"]
    for start in starts:
        try:
            value, _end = decoder.raw_decode(cleaned[start:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("Could not parse a JSON object from judge response")


def validate_payload(task: str, payload: dict[str, Any], expected_ids: set[str]) -> dict[str, Any]:
    config = TASK_CONFIG[task]
    id_field = config["id_field"]
    items = payload.get("ratings")
    if items is None:
        for alias in (f"{task}_ratings", "items", "edges", "answers", "hypotheses"):
            if alias in payload:
                items = payload[alias]
                break
    if isinstance(items, dict):
        normalized_items = []
        for item_id, value in items.items():
            if isinstance(value, dict):
                normalized_items.append({id_field: item_id, **value})
        items = normalized_items
    if not isinstance(items, list):
        raise ValueError("Response lacks a ratings array")
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get(id_field, "")).strip()
        if item_id not in expected_ids or item_id in by_id:
            raise ValueError(f"Unexpected or duplicate {id_field}: {item_id!r}")
        rating: dict[str, Any] = {id_field: item_id}
        for field, (minimum, maximum) in config["score_fields"].items():
            value = item.get(field)
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"[{item_id}] invalid {field}: {value!r}")
            rating[field] = value
        rating["notes"] = str(item.get("notes", "")).strip()
        by_id[item_id] = rating
    if set(by_id) != expected_ids:
        raise ValueError(f"Missing ratings: {sorted(expected_ids - set(by_id))}")

    preference = ""
    pairwise_reason = ""
    if task in {"hypothesis", "answer"}:
        preference = str(payload.get("preferred_item_id", "")).strip()
        if preference not in expected_ids | {"tie"}:
            raise ValueError(f"Invalid preferred_item_id: {preference!r}")
        pairwise_reason = str(payload.get("pairwise_reason", "")).strip()
    return {
        "ratings": [by_id[item_id] for item_id in sorted(by_id)],
        "preferred_item_id": preference,
        "pairwise_reason": pairwise_reason,
    }


def init_client(provider: str, model: str) -> LLMClient:
    if provider == "google" and gemini_api_disabled():
        raise RuntimeError(
            "Gemini judge is disabled by DISABLE_GEMINI_API; use "
            "--provider local --model medgemma:27b."
        )
    key_by_provider = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "google": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "local": os.getenv("LOCAL_LLM_API_KEY") or "local-dummy-key",
    }
    local_base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    if not local_base_url.endswith("/v1"):
        local_base_url += "/v1"
    base_by_provider = {
        "openai": OPENAI_BASE_URL,
        "google": GEMINI_OPENAI_BASE_URL,
        "anthropic": ANTHROPIC_BASE_URL,
        "local": local_base_url,
    }
    api_key = key_by_provider.get(provider)
    if not api_key:
        raise RuntimeError(f"API key for provider {provider!r} is missing")
    client = LLMClient()
    client.initialize_client(
        provider=provider,
        api_key=api_key,
        base_url=base_by_provider[provider],
        model=model,
    )
    return client


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[TRUNCATED FOR JUDGE INPUT]"


def build_records(task: str, rows: list[dict[str, str]], max_evidence_chars: int) -> list[dict[str, str]]:
    if task == "edge":
        return [
            {
                "edge_id": row["edge_id"],
                "source": row["source"],
                "relation_type": row["relation_type"],
                "target": row["target"],
                "pmids": row.get("pmids", ""),
                "supporting_titles": row.get("supporting_titles", ""),
                "evidence_quotes": row.get("evidence_quotes", ""),
                "supporting_abstracts": _truncate(
                    row.get("supporting_abstracts", ""), max_evidence_chars
                ),
            }
            for row in rows
        ]
    if task == "hidden_claim":
        return [
            {
                "hidden_claim_id": row["hidden_claim_id"],
                "candidate_claim": row["candidate_claim"],
                "candidate_block": row.get("candidate_block", ""),
                "path_evidence": _truncate(
                    row.get("path_evidence_json", ""), max_evidence_chars
                ),
                "comparison_answer": row.get("comparison_answer", ""),
            }
            for row in rows
        ]
    id_field = TASK_CONFIG[task]["id_field"]
    text_field = "answer_text"
    return [{id_field: row[id_field], text_field: row[text_field]} for row in rows]


def build_prompt(task: str, question: str, records: list[dict[str, str]]) -> str:
    config = TASK_CONFIG[task]
    id_field = config["id_field"]
    score_description = ", ".join(
        f"{field} ({minimum}-{maximum} integer)"
        for field, (minimum, maximum) in config["score_fields"].items()
    )
    preference = ""
    if task in {"hypothesis", "answer"}:
        preference = (
            " Also return preferred_item_id (one supplied ID or 'tie') and pairwise_reason."
        )
    shared_context = ""
    if task == "hidden_claim" and records:
        comparison_answer = records[0].get("comparison_answer", "")
        for record in records:
            record.pop("comparison_answer", None)
        shared_context = f"\n\nAnonymous comparison answer:\n{comparison_answer}"
    return (
        f"Question:\n{question}\n\nRate every item independently. Return an object with `ratings`, "
        f"exactly one entry per item. Each entry must contain {id_field}, {score_description}, "
        f"and notes of at most 30 words per item.{preference}{shared_context}\n\nItems:\n"
        + json.dumps(records, ensure_ascii=False)
    )


def atomic_write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def rate_batch(
    client: LLMClient,
    task: str,
    question: str,
    rows: list[dict[str, str]],
    max_evidence_chars: int,
    retries: int,
) -> tuple[dict[str, Any], str]:
    records = build_records(task, rows, max_evidence_chars)
    expected = {row[TASK_CONFIG[task]["id_field"]] for row in rows}
    prompt = build_prompt(task, question, records)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            raw = client.chat_completion_text(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPTS[task]},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=6000,
                timeout=600,
                response_format={"type": "json_object"}
                if client.provider != "anthropic"
                else None,
            )
            try:
                return validate_payload(task, parse_json_object(raw), expected), raw
            except Exception as exc:
                # Preserve enough response structure for diagnosis so callers can use retries=1
                # instead of spending tokens repeatedly on the same schema mismatch.
                raise ValueError(f"{exc}; response preview={raw[:800]!r}") from exc
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Judge failed after {retries} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=sorted(TASK_CONFIG), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument(
        "--item-file",
        type=Path,
        help="Optional newline-delimited item IDs. Only these blinded items are sent to the judge.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Hard cap after filtering (0 means no cap), useful for token-budgeted calibration.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact prompt-character and rough token estimate without calling an API.",
    )
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--max-evidence-chars", type=int, default=8000)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    load_dotenv(".env", override=True)
    model = args.model or DEFAULT_MODELS[args.provider]
    checkpoint_dir = args.checkpoint_dir or args.output.parent / (
        f"{args.output.stem}_checkpoints"
    )
    manifest_path = args.manifest or args.output.with_suffix(".manifest.json")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    with args.input.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    config = TASK_CONFIG[args.task]
    id_field = config["id_field"]
    for field in ["rater_id", *config["score_fields"], "preferred_answer_id", "preferred_hypothesis_id", "pairwise_reason", "notes"]:
        if field not in fields:
            fields.append(field)

    # Preserve ratings from a prior partial invocation even when the resumed command selects only
    # the remaining questions/items. Checkpoints remain authoritative for selected batches, while
    # this overlay prevents an output rewrite from blanking already-completed unselected rows.
    if args.output.exists():
        with args.output.open(newline="", encoding="utf-8") as handle:
            prior_rows = list(csv.DictReader(handle))
        prior_by_id = {row.get(id_field, ""): row for row in prior_rows if row.get(id_field)}
        rating_fields = [
            "rater_id",
            *config["score_fields"],
            "preferred_answer_id",
            "preferred_hypothesis_id",
            "pairwise_reason",
            "notes",
        ]
        for row in rows:
            prior = prior_by_id.get(row[id_field])
            if prior and prior.get("rater_id", "").strip():
                for field in rating_fields:
                    if field in prior:
                        row[field] = prior[field]

    selected_item_ids: set[str] = set()
    if args.item_file:
        selected_item_ids = {
            line.strip()
            for line in args.item_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    eligible_rows = [
        row
        for row in rows
        if (not selected_item_ids or row[id_field] in selected_item_ids)
        and (not args.only or row["question_id"] in set(args.only))
    ]
    if args.max_items > 0:
        eligible_rows = eligible_rows[: args.max_items]
    if not eligible_rows:
        raise ValueError("No worksheet rows matched the item/question filters")
    if selected_item_ids:
        missing_items = selected_item_ids - {row[id_field] for row in rows}
        if missing_items:
            raise ValueError(f"Item IDs not found in worksheet: {sorted(missing_items)}")

    by_question: dict[str, list[dict[str, str]]] = {}
    for row in eligible_rows:
        by_question.setdefault(row["question_id"], []).append(row)
    selected = sorted(by_question)
    row_by_id = {row[id_field]: row for row in rows}

    estimated_chars = 0
    for qid in selected:
        question_rows = by_question[qid]
        batch_size = len(question_rows) if args.task != "edge" else max(1, args.batch_size)
        for index in range(0, len(question_rows), batch_size):
            batch = question_rows[index : index + batch_size]
            estimated_chars += len(SYSTEM_PROMPTS[args.task]) + len(
                build_prompt(
                    args.task,
                    batch[0]["question"],
                    build_records(args.task, batch, args.max_evidence_chars),
                )
            )
    print(
        f"Token budget estimate: {len(eligible_rows)} items, {estimated_chars} prompt chars, "
        f"~{round(estimated_chars / 4)} input tokens (rough 4-char estimate).",
        flush=True,
    )
    if args.dry_run:
        return

    client = init_client(args.provider, model)
    started_at = datetime.now(timezone.utc).isoformat()
    completed_batches = 0

    for q_index, qid in enumerate(selected, 1):
        question_rows = by_question[qid]
        batch_size = len(question_rows) if args.task != "edge" else max(1, args.batch_size)
        batches = [question_rows[i : i + batch_size] for i in range(0, len(question_rows), batch_size)]
        for batch_index, batch in enumerate(batches, 1):
            records = build_records(args.task, batch, args.max_evidence_chars)
            input_hash = hashlib.sha256(
                json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            checkpoint = checkpoint_dir / f"{qid}-B{batch_index:02d}.json"
            result: dict[str, Any] | None = None
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                if (
                    saved.get("provider") == args.provider
                    and saved.get("model") == model
                    and saved.get("input_sha256") == input_hash
                ):
                    result = saved["result"]
            if result is None:
                print(
                    f"[{q_index}/{len(selected)}] {qid} batch {batch_index}/{len(batches)} "
                    f"via {args.provider}:{model}",
                    flush=True,
                )
                result, raw = rate_batch(
                    client,
                    args.task,
                    batch[0]["question"],
                    batch,
                    args.max_evidence_chars,
                    args.retries,
                )
                payload = {
                    "task": args.task,
                    "question_id": qid,
                    "batch": batch_index,
                    "provider": args.provider,
                    "model": model,
                    "input_sha256": input_hash,
                    "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "usage": dict(getattr(client, "last_completion_usage", {}) or {}),
                    "rated_at": datetime.now(timezone.utc).isoformat(),
                    "result": result,
                }
                tmp = checkpoint.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                tmp.replace(checkpoint)

            preference_field = (
                "preferred_answer_id" if args.task == "answer" else "preferred_hypothesis_id"
            )
            for rating in result["ratings"]:
                row = row_by_id[rating[id_field]]
                row["rater_id"] = f"{args.provider}:{model}"
                for field in config["score_fields"]:
                    row[field] = str(rating[field])
                row["notes"] = rating["notes"]
                if args.task in {"answer", "hypothesis"}:
                    row[preference_field] = result["preferred_item_id"]
                    row["pairwise_reason"] = result["pairwise_reason"]
            completed_batches += 1
            atomic_write_csv(args.output, fields, rows)

    actual_usage: dict[str, int] = {}
    for checkpoint in checkpoint_dir.glob("*.json"):
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if saved.get("provider") != args.provider or saved.get("model") != model:
            continue
        for field, value in (saved.get("usage") or {}).items():
            if isinstance(value, int):
                actual_usage[field] = actual_usage.get(field, 0) + value

    manifest = {
        "reviewer_type": "AI",
        "human_expert_review_claimed": False,
        "blinded": True,
        "task": args.task,
        "provider": args.provider,
        "model": model,
        "input_file": str(args.input),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "output_file": str(args.output),
        "question_count": len(selected),
        "row_count": sum(len(by_question[qid]) for qid in selected),
        "estimated_prompt_chars": estimated_chars,
        "estimated_input_tokens_rough": round(estimated_chars / 4),
        "actual_api_usage_from_checkpoints": actual_usage or None,
        "completed_batches": completed_batches,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
