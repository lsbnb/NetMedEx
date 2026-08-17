#!/usr/bin/env python3
"""Analyze the frozen path-positive efficacy benchmark at the question level."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

try:
    from evaluation.metrics import _bootstrap_mean_ci, _sign_test_p_value
except ModuleNotFoundError:
    from metrics import _bootstrap_mean_ci, _sign_test_p_value


SCORES = (
    "correctness", "completeness", "relevance", "grounding",
    "mechanistic_coherence", "research_value",
)
SYSTEM_TO_ARM = {
    "closed_book_llm": "A",
    "traditional_text_rag": "B",
    "text_rag_kg_reranking": "C",
    "kg_expansion_reranking_path_answer": "D",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def score_panel(path: Path) -> tuple[dict, dict[tuple[str, str], float]]:
    rows = read_csv(path)
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    fields: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        arm = SYSTEM_TO_ARM[row["system"]]
        qid = row["question_id"]
        values[(qid, arm)].append(mean(float(row[field]) for field in SCORES))
        for field in SCORES:
            fields[(arm, field)].append(float(row[field]))
    per_question = {key: mean(item) for key, item in values.items()}
    qids = sorted({qid for qid, _arm in per_question})
    summary = {}
    for arm in "ABCD":
        arm_values = [per_question[(qid, arm)] for qid in qids]
        summary[arm] = {
            "mean": round(mean(arm_values), 4),
            "median": round(median(arm_values), 4),
            "fields": {
                field: round(mean(fields[(arm, field)]), 4) for field in SCORES
            },
        }
    return summary, per_question


def paired(per_question: dict[tuple[str, str], float], ids: list[str], arm: str) -> dict:
    diffs = [per_question[(qid, arm)] - per_question[(qid, "B")] for qid in ids]
    point, low, high = _bootstrap_mean_ci(diffs)
    return {
        "direction": f"{arm}-B", "n": len(diffs), "mean_diff": round(point, 4),
        "bootstrap_95ci": [round(low, 4), round(high, 4)],
        "sign_test_p": round(_sign_test_p_value(diffs), 6),
        "wins": sum(x > 1e-9 for x in diffs),
        "losses": sum(x < -1e-9 for x in diffs),
        "ties": sum(abs(x) <= 1e-9 for x in diffs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    all_scores, all_per_question = score_panel(args.run_dir / "judge_ratings_long.csv")
    external_scores, external_per_question = score_panel(
        args.run_dir / "external_judge_ratings_long.csv"
    )
    audit = read_csv(args.benchmark_dir / "candidate_audit.csv")
    strata = {"all": sorted(row["question_id"] for row in audit)}
    for category in ("direct", "multi_hop_same_pmid", "multi_hop_cross_pmid"):
        strata[category] = sorted(
            row["question_id"] for row in audit if row["category"] == category
        )

    structure = {
        "question_count": len(audit), "tier_a_path_positive": 0,
        "reranking_intervened": 0, "expansion_added_documents": 0,
        "expansion_question_count": 0, "total_added_documents": 0,
    }
    operations = {}
    for arm in "ABCD":
        metrics = read_csv(args.run_dir / f"arm_{arm}" / "run_metrics.csv")
        operations[arm] = {
            "total_seconds": round(sum(float(row["total"]) for row in metrics), 2),
            "median_seconds": round(median(float(row["total"]) for row in metrics), 2),
            "input_tokens": sum(int(row.get("tokens_input_tokens") or 0) for row in metrics),
            "output_tokens": sum(int(row.get("tokens_output_tokens") or 0) for row in metrics),
        }
    for path in sorted((args.run_dir / "arm_D/questions").glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        exposure = result.get("evidence_exposure") or {}
        expansion = exposure.get("kg_expansion") or {}
        added = int(expansion.get("added_document_count") or 0)
        structure["tier_a_path_positive"] += result.get("graph", {}).get("path_count", 0) > 0
        structure["reranking_intervened"] += bool(
            (exposure.get("reranking") or {}).get("boosted_pmids")
        )
        structure["expansion_question_count"] += added > 0
        structure["total_added_documents"] += added

    payload = {
        "design_note": "Conditional path-positive efficacy set; not an ITT estimate.",
        "strata": {key: len(value) for key, value in strata.items()},
        "three_judge_scores": all_scores,
        "three_judge_paired_vs_B": {
            name: {arm: paired(all_per_question, ids, arm) for arm in ("A", "C", "D")}
            for name, ids in strata.items()
        },
        "external_judges_scores": external_scores,
        "external_judges_paired_vs_B": {
            name: {
                arm: paired(external_per_question, ids, arm) for arm in ("A", "C", "D")
            }
            for name, ids in strata.items()
        },
        "structural_intervention": structure,
        "operations": operations,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
