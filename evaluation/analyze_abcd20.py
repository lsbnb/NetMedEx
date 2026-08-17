#!/usr/bin/env python3
"""Reproducible analysis for a completed four-arm, three-judge pilot."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

try:
    from evaluation.metrics import _bootstrap_mean_ci, _sign_test_p_value, score_retrieval
except ModuleNotFoundError:
    from metrics import _bootstrap_mean_ci, _sign_test_p_value, score_retrieval


SCORES = (
    "correctness", "completeness", "relevance", "grounding",
    "mechanistic_coherence", "research_value",
)
ARM_SYSTEMS = {
    "A": "closed_book_llm",
    "B": "traditional_text_rag",
    "C": "text_rag_kg_reranking",
    "D": "kg_expansion_reranking_path_answer",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def paired_summary(by_question: dict[tuple[str, str], float], first: str, second: str,
                   qids: list[str]) -> dict:
    diffs = [by_question[(qid, first)] - by_question[(qid, second)] for qid in qids]
    point, lo, hi = _bootstrap_mean_ci(diffs)
    return {
        "direction": f"{first} minus {second}", "n": len(diffs),
        "mean_diff": point, "bootstrap_95ci": [lo, hi],
        "sign_test_p": _sign_test_p_value(diffs),
        "wins": sum(value > 1e-9 for value in diffs),
        "losses": sum(value < -1e-9 for value in diffs),
        "ties": sum(abs(value) <= 1e-9 for value in diffs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, default=Path("evaluation/formal/qrels.csv"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    ratings = read_csv(args.run_dir / "judge_ratings_long.csv")
    key = {row["answer_id"]: row["system"] for row in read_csv(args.run_dir / "blinded_answer_key.csv")}
    system_to_arm = {system: arm for arm, system in ARM_SYSTEMS.items()}
    qids = sorted({row["question_id"] for row in ratings})

    item_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    field_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    judge_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in ratings:
        arm = system_to_arm[row["system"]]
        values = [float(row[field]) for field in SCORES]
        item_values[(row["question_id"], arm)].append(mean(values))
        judge_values[(row["judge"], arm)].append(mean(values))
        for field in SCORES:
            field_values[(arm, field, row["question_id"])].append(float(row[field]))
    per_question = {key_: mean(values) for key_, values in item_values.items()}

    answer_summary = {}
    for arm in ARM_SYSTEMS:
        arm_values = [per_question[(qid, arm)] for qid in qids]
        answer_summary[arm] = {
            "system": ARM_SYSTEMS[arm],
            "overall_mean": round(mean(arm_values), 4),
            "overall_median": round(median(arm_values), 4),
            "fields": {
                field: round(mean(
                    mean(field_values[(arm, field, qid)]) for qid in qids
                ), 4)
                for field in SCORES
            },
            "by_judge": {
                judge: round(mean(values), 4)
                for (judge, current_arm), values in judge_values.items()
                if current_arm == arm
            },
        }

    path_qids, expansion_qids = [], []
    for path in sorted((args.run_dir / "arm_D" / "questions").glob("Q*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["graph"]["path_count"] > 0:
            path_qids.append(path.parent.name)
        if result["evidence_exposure"]["kg_expansion"]["added_pmids"]:
            expansion_qids.append(path.parent.name)
    strata = {
        "all_20": qids,
        "tier_a_path_enabled_5": path_qids,
        "no_tier_a_path_15": sorted(set(qids) - set(path_qids)),
        "expansion_triggered_3": expansion_qids,
        "no_expansion_17": sorted(set(qids) - set(expansion_qids)),
    }
    comparisons = {
        name: {
            arm: paired_summary(per_question, arm, "B", ids)
            for arm in ("A", "C", "D")
        }
        for name, ids in strata.items()
        if ids
    }

    qrels = read_csv(args.qrels)
    retrieval_rows = []
    for arm in ("B", "C", "D"):
        for row in read_csv(args.run_dir / f"arm_{arm}" / "retrieval_runs.csv"):
            retrieval_rows.append({**row, "system": arm})
    retrieval = score_retrieval(qrels, retrieval_rows)

    operations = {}
    for arm in ARM_SYSTEMS:
        rows = read_csv(args.run_dir / f"arm_{arm}" / "run_metrics.csv")
        operations[arm] = {
            "total_seconds": round(sum(float(row["total"]) for row in rows), 2),
            "median_seconds": round(median(float(row["total"]) for row in rows), 2),
            "input_tokens": sum(int(row.get("tokens_input_tokens") or 0) for row in rows),
            "output_tokens": sum(int(row.get("tokens_output_tokens") or 0) for row in rows),
            "total_tokens": sum(int(row.get("tokens_total_tokens") or 0) for row in rows),
        }

    payload = {
        "question_count": len(qids), "rating_count": len(ratings),
        "scores": answer_summary, "strata_question_ids": strata,
        "paired_vs_B": comparisons, "retrieval": retrieval,
        "operations": operations,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
