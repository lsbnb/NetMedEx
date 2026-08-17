#!/usr/bin/env python3
"""Merge blinded AI judge outputs, compute consensus, reliability, and paired preferences."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

try:
    from evaluation.metrics import (
        _bootstrap_mean_ci,
        _sign_test_p_value,
        fleiss_kappa,
        krippendorff_alpha,
    )
    from evaluation.rate_ai_panel import TASK_CONFIG
except ModuleNotFoundError:  # Allow `python evaluation/aggregate_ai_panel.py ...`.
    from metrics import _bootstrap_mean_ci, _sign_test_p_value, fleiss_kappa, krippendorff_alpha
    from rate_ai_panel import TASK_CONFIG


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def parse_rating_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--rating must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    if not label.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--rating must be LABEL=PATH")
    return label.strip(), Path(raw_path)


def majority_or_median(values: list[int], minimum: int, maximum: int) -> int:
    if (minimum, maximum) == (0, 1):
        counts = Counter(values)
        if counts[0] == counts[1]:
            return int(round(mean(values)))
        return counts.most_common(1)[0][0]
    return int(median(values))


def aggregate(
    task: str,
    rating_files: list[tuple[str, Path]],
    key_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    config = TASK_CONFIG[task]
    id_field = config["id_field"]
    score_fields = config["score_fields"]
    key = {}
    if key_path:
        key = {row[id_field]: row["system"] for row in read_csv(key_path)}

    long_rows: list[dict[str, Any]] = []
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    preferences: dict[tuple[str, str], str] = {}
    for judge_label, path in rating_files:
        for source in read_csv(path):
            item_id = source.get(id_field, "")
            if not item_id or any(source.get(field, "") == "" for field in score_fields):
                continue
            row: dict[str, Any] = {
                id_field: item_id,
                "question_id": source["question_id"],
                "system": key.get(item_id, source.get("system", "netmedex_hybrid_rag")),
                "judge": judge_label,
                "rater_id": source.get("rater_id") or judge_label,
                "notes": source.get("notes", ""),
            }
            for field in score_fields:
                row[field] = int(source[field])
            long_rows.append(row)
            by_item[item_id].append(row)

            if task in {"answer", "hypothesis"}:
                preference_field = (
                    "preferred_answer_id" if task == "answer" else "preferred_hypothesis_id"
                )
                preference = source.get(preference_field, "")
                if preference:
                    preferences[(judge_label, source["question_id"])] = preference

    consensus_rows: list[dict[str, Any]] = []
    for item_id, ratings in sorted(by_item.items()):
        consensus: dict[str, Any] = {
            id_field: item_id,
            "question_id": ratings[0]["question_id"],
            "system": ratings[0]["system"],
            "judge_count": len(ratings),
        }
        for field, (minimum, maximum) in score_fields.items():
            values = [int(row[field]) for row in ratings]
            consensus[field] = majority_or_median(values, minimum, maximum)
            consensus[f"{field}_mean"] = round(mean(values), 4)
            consensus[f"{field}_unanimous"] = int(len(set(values)) == 1)
        consensus_rows.append(consensus)

    reliability: dict[str, Any] = {}
    for field, (minimum, maximum) in score_fields.items():
        values = [
            [int(row[field]) for row in ratings]
            for ratings in by_item.values()
            if len(ratings) >= 2
        ]
        reliability[field] = {
            "n_multi_rated_items": len(values),
            "rater_count": min((len(item) for item in values), default=0),
            "fleiss_kappa": fleiss_kappa(values)
            if values and min(len(item) for item in values) >= 3
            else None,
            "krippendorff_alpha": krippendorff_alpha(
                values, level="nominal" if (minimum, maximum) == (0, 1) else "ordinal"
            ),
        }

    summary: dict[str, Any] = {
        "task": task,
        "judges": [label for label, _path in rating_files],
        "rated_rows": len(long_rows),
        "unique_items": len(by_item),
        "reliability": reliability,
    }

    if key and task in {"answer", "hypothesis"}:
        systems = sorted(set(key.values()))
        per_question_system: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in long_rows:
            per_question_system[(row["question_id"], row["system"])].append(
                mean(float(row[field]) for field in score_fields)
            )
        if len(systems) == 2:
            qids = sorted({qid for qid, _system in per_question_system})
            diffs = []
            for qid in qids:
                first = per_question_system.get((qid, systems[0]))
                second = per_question_system.get((qid, systems[1]))
                if first and second:
                    diffs.append(mean(first) - mean(second))
            if diffs:
                point, lo, hi = _bootstrap_mean_ci(diffs)
                summary["paired_score_comparison"] = {
                    "systems": systems,
                    "diff_direction": f"{systems[0]} minus {systems[1]}",
                    "n_questions": len(diffs),
                    "mean_diff": point,
                    "bootstrap_95ci": [lo, hi],
                    "sign_test_p": _sign_test_p_value(diffs),
                }

        preference_counts = Counter()
        preference_votes_by_question: dict[str, list[str]] = defaultdict(list)
        for (_judge, qid), preferred_id in preferences.items():
            outcome = "tie" if preferred_id == "tie" else key.get(preferred_id, "invalid")
            preference_counts[outcome] += 1
            preference_votes_by_question[qid].append(outcome)
        question_consensus = Counter()
        for outcomes in preference_votes_by_question.values():
            counts = Counter(outcomes)
            top = counts.most_common()
            if len(top) > 1 and top[0][1] == top[1][1]:
                question_consensus["tie"] += 1
            else:
                question_consensus[top[0][0]] += 1
        summary["pairwise_preferences"] = {
            "raw_judge_votes": dict(preference_counts),
            "question_level_consensus": dict(question_consensus),
        }

    return long_rows, consensus_rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=sorted(TASK_CONFIG), required=True)
    parser.add_argument("--rating", action="append", type=parse_rating_arg, required=True)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--output-long", type=Path, required=True)
    parser.add_argument("--output-consensus", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    args = parser.parse_args()

    long_rows, consensus_rows, summary = aggregate(args.task, args.rating, args.key)
    config = TASK_CONFIG[args.task]
    id_field = config["id_field"]
    score_fields = list(config["score_fields"])
    write_csv(
        args.output_long,
        [id_field, "question_id", "system", "judge", "rater_id", *score_fields, "notes"],
        long_rows,
    )
    consensus_fields = [id_field, "question_id", "system", "judge_count"]
    for field in score_fields:
        consensus_fields.extend([field, f"{field}_mean", f"{field}_unanimous"])
    write_csv(args.output_consensus, consensus_fields, consensus_rows)
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
