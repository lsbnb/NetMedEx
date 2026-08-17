#!/usr/bin/env python3
"""Paired and endpoint-clustered analysis for the structured D revision."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

try:
    from evaluation.metrics import _bootstrap_mean_ci, _sign_test_p_value
except ModuleNotFoundError:
    from metrics import _bootstrap_mean_ci, _sign_test_p_value


FIELDS = ("correctness", "completeness", "relevance", "grounding", "mechanistic_coherence", "research_value")
SHORT = {
    "traditional_text_rag": "B", "text_rag_kg_reranking": "C",
    "legacy_path_answer": "D_v1", "structured_gated_path_answer": "D_v2",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def comparison(diffs: list[float], unit: str) -> dict:
    point, lo, hi = _bootstrap_mean_ci(diffs)
    return {
        "unit": unit, "n": len(diffs), "mean_diff": round(point, 4),
        "bootstrap_95ci": [round(lo, 4), round(hi, 4)],
        "wins": sum(x > 1e-9 for x in diffs), "losses": sum(x < -1e-9 for x in diffs),
        "ties": sum(abs(x) <= 1e-9 for x in diffs),
        "sign_test_p": round(_sign_test_p_value(diffs), 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = rows(args.ratings)
    audit = {row["question_id"]: row for row in rows(args.audit)}
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    field_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in raw:
        system = SHORT[row["system"]]
        values[(row["question_id"], system)].append(mean(float(row[f]) for f in FIELDS))
        for field in FIELDS:
            field_values[(system, field)].append(float(row[field]))
    perq = {key: mean(item) for key, item in values.items()}
    qids = sorted({key[0] for key in perq})
    scores = {
        system: {
            "mean": round(mean(perq[(qid, system)] for qid in qids), 4),
            "fields": {field: round(mean(field_values[(system, field)]), 4) for field in FIELDS},
        }
        for system in ("B", "C", "D_v1", "D_v2")
    }
    contrasts = {}
    for first, second in (("C", "B"), ("D_v1", "B"), ("D_v2", "B"), ("D_v2", "D_v1")):
        question_diffs = [perq[(qid, first)] - perq[(qid, second)] for qid in qids]
        cluster_members: dict[str, list[float]] = defaultdict(list)
        for qid, diff in zip(qids, question_diffs):
            cluster_members[audit[qid]["source_question_id"]].append(diff)
        cluster_diffs = [mean(item) for item in cluster_members.values()]
        leave_one_cluster_out = [
            mean(value for cluster, values_ in cluster_members.items() if cluster != omitted for value in [mean(values_)])
            for omitted in cluster_members
        ]
        contrasts[f"{first}-{second}"] = {
            "question_level": comparison(question_diffs, "question"),
            "endpoint_cluster_level": comparison(cluster_diffs, "source_endpoint_cluster"),
            "cluster_count": len(cluster_members),
            "leave_one_cluster_out_range": [round(min(leave_one_cluster_out), 4), round(max(leave_one_cluster_out), 4)],
        }
    payload = {"scores": scores, "contrasts": contrasts}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
