from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from math import comb
from pathlib import Path
from statistics import mean, median
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _as_float(value: str | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _split_values(value: str | None) -> list[str]:
    if value is None:
        return []
    parts = [part.strip() for part in str(value).split(";")]
    return [part for part in parts if part]


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(median(values), 4) if values else None


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(0.9 * len(ordered)) - 1
    return round(ordered[max(0, min(index, len(ordered) - 1))], 4)


def _dcg(relevances: list[float]) -> float:
    return sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(relevances))


def _jaccard(a: set[str], b: set[str]) -> float | None:
    if not a and not b:
        return None
    union = a | b
    if not union:
        return None
    return round(len(a & b) / len(union), 4)


def _cluster_means_by_id(
    rows: list[dict[str, str]], id_field: str, field: str
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        item_id = row.get(id_field)
        if not item_id:
            continue
        grouped[item_id].append(_as_float(row.get(field)))
    return {item_id: mean(values) for item_id, values in grouped.items() if values}


def _path_signature(row: dict[str, str]) -> tuple[str, ...]:
    return (
        str(row.get("source", "")).strip(),
        str(row.get("bridge", "")).strip(),
        str(row.get("target", "")).strip(),
        str(row.get("relation_1", "")).strip().lower(),
        str(row.get("relation_2", "")).strip().lower(),
        str(row.get("direction_1", "")).strip().lower(),
        str(row.get("direction_2", "")).strip().lower(),
    )


def _path_pmids(row: dict[str, str]) -> set[str]:
    return set(_split_values(row.get("pmids") or row.get("supporting_pmids") or row.get("evidence_pmids")))


def cohens_kappa(a: list[int], b: list[int], weighted: str | None = None) -> float | None:
    """Cohen's kappa between two raters' paired categorical judgments.

    `weighted` is None (plain kappa -- appropriate for nominal/binary categories like
    biologically_meaningful 0/1), "linear", or "quadratic" (appropriate for ordinal categories
    like a 1-5 novelty score, where a 3-vs-4 disagreement should count for less than a 1-vs-5
    disagreement). Uses the standard disagreement-weight formulation, which reduces to plain
    Cohen's kappa when every off-diagonal weight is 1: kappa = 1 - (weighted observed
    disagreement) / (weighted expected disagreement under independence).
    """
    n = len(a)
    if n == 0 or n != len(b):
        return None
    categories = sorted(set(a) | set(b))
    k = len(categories)
    if k < 2:
        return None  # no variation in either rater -- kappa is undefined, not 1.0

    idx = {c: i for i, c in enumerate(categories)}
    confusion = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        confusion[idx[x]][idx[y]] += 1
    row_totals = [sum(row) for row in confusion]
    col_totals = [sum(confusion[r][c] for r in range(k)) for c in range(k)]

    if weighted is None:
        weights = [[0.0 if i == j else 1.0 for j in range(k)] for i in range(k)]
    elif weighted == "linear":
        weights = [[abs(i - j) / (k - 1) for j in range(k)] for i in range(k)]
    elif weighted == "quadratic":
        weights = [[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)]
    else:
        raise ValueError(f"Unknown weighting scheme: {weighted}")

    observed_disagreement = sum(
        weights[i][j] * confusion[i][j] for i in range(k) for j in range(k)
    ) / n
    expected_disagreement = sum(
        weights[i][j] * row_totals[i] * col_totals[j] for i in range(k) for j in range(k)
    ) / (n * n)
    if expected_disagreement == 0:
        return None  # both raters always chose the same single category -- undefined by convention
    return round(1 - observed_disagreement / expected_disagreement, 4)


def fleiss_kappa(item_ratings: list[list[int]]) -> float | None:
    """Fleiss' kappa for complete multi-rater categorical judgments."""
    complete = [values for values in item_ratings if len(values) >= 2]
    if not complete:
        return None
    rater_counts = {len(values) for values in complete}
    if len(rater_counts) != 1:
        return None
    n_raters = rater_counts.pop()
    categories = sorted({value for values in complete for value in values})
    if len(categories) < 2:
        return None
    category_totals = {category: 0 for category in categories}
    observed = []
    for values in complete:
        counts = {category: values.count(category) for category in categories}
        for category, count in counts.items():
            category_totals[category] += count
        observed.append(
            (sum(count * count for count in counts.values()) - n_raters)
            / (n_raters * (n_raters - 1))
        )
    p_bar = mean(observed)
    total_ratings = len(complete) * n_raters
    p_e = sum((count / total_ratings) ** 2 for count in category_totals.values())
    if p_e == 1:
        return None
    return round((p_bar - p_e) / (1 - p_e), 4)


def krippendorff_alpha(
    item_ratings: list[list[int]], level: str = "nominal"
) -> float | None:
    """Krippendorff-style alpha using pairwise disagreement with missing-value support.

    `ordinal` uses squared category-rank distance, appropriate for the evaluation's 1-5 scales;
    `nominal` gives every unequal pair distance one, appropriate for binary edge judgments.
    """
    complete = [values for values in item_ratings if len(values) >= 2]
    pooled = [value for values in complete for value in values]
    if len(pooled) < 2:
        return None
    categories = sorted(set(pooled))
    if len(categories) < 2:
        return None
    ranks = {category: index for index, category in enumerate(categories)}

    def distance(a: int, b: int) -> float:
        if level == "nominal":
            return 0.0 if a == b else 1.0
        if level == "ordinal":
            return float((ranks[a] - ranks[b]) ** 2)
        raise ValueError(f"Unknown measurement level: {level}")

    observed_sum = 0.0
    observed_pairs = 0
    for values in complete:
        for i, first in enumerate(values):
            for second in values[i + 1 :]:
                observed_sum += distance(first, second)
                observed_pairs += 1
    expected_sum = 0.0
    expected_pairs = 0
    for i, first in enumerate(pooled):
        for second in pooled[i + 1 :]:
            expected_sum += distance(first, second)
            expected_pairs += 1
    if not observed_pairs or not expected_pairs:
        return None
    observed = observed_sum / observed_pairs
    expected = expected_sum / expected_pairs
    if expected == 0:
        return None
    return round(1 - observed / expected, 4)


def _multi_rater_values(
    rows: list[dict[str, str]], id_field: str, field: str
) -> tuple[list[str], list[list[int]], list[str]]:
    raters = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
    by_item: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        item_id = row.get(id_field)
        rater = row.get("rater_id")
        value = row.get(field)
        if item_id and rater and value not in {None, ""}:
            by_item[item_id][rater] = int(round(_as_float(value)))
    item_ids = sorted(item_id for item_id, values in by_item.items() if len(values) >= 2)
    return item_ids, [[by_item[item_id][rater] for rater in raters if rater in by_item[item_id]] for item_id in item_ids], raters


def _bootstrap_mean_ci(
    values: list[float], n_resamples: int = 10000, ci: float = 0.95, seed: int = 42
) -> tuple[float, float | None, float | None]:
    """Bootstrap CI on the mean of `values`, resampling whole values (not sub-values) with
    replacement. Each entry in `values` should be an independent cluster-level statistic (e.g. one
    per-question paired difference), not a raw per-edge/per-rating observation, so the resampling
    respects within-question correlation instead of pretending every row is independent.

    Fixed seed so results are reproducible run-to-run (this is a report artifact, not a live
    simulation) -- matches the fixed-seed convention already used for blinding assignment
    elsewhere in this evaluation workspace.
    """
    point = round(mean(values), 4)
    n = len(values)
    if n < 2:
        return point, None, None
    rng = random.Random(seed)
    resampled_means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        resampled_means.append(mean(sample))
    resampled_means.sort()
    alpha = (1 - ci) / 2
    lo_index = int(alpha * n_resamples)
    hi_index = int((1 - alpha) * n_resamples) - 1
    return point, round(resampled_means[lo_index], 4), round(resampled_means[hi_index], 4)


def _sign_test_p_value(diffs: list[float]) -> float | None:
    """Two-sided exact sign test p-value: is the split of positive vs. negative paired diffs
    distinguishable from a fair coin flip? Ties (diff == 0) are excluded, per the standard sign
    test convention. Deliberately not a Wilcoxon signed-rank test -- that would need SciPy, and
    this evaluation workspace stays dependency-light by design (see score_retrieval's manual DCG/
    bpref implementations); the sign test needs only stdlib math.comb and is a reasonable,
    if less powerful, complement to the bootstrap CI above.
    """
    nonzero = [d for d in diffs if d != 0]
    n = len(nonzero)
    if n == 0:
        return None
    positives = sum(1 for d in nonzero if d > 0)
    k = min(positives, n - positives)
    p_value = sum(comb(n, i) for i in range(0, k + 1)) * 2 / (2**n)
    return round(min(p_value, 1.0), 4)


def _bpref(ranked_pmids: list[str], gold: dict[str, float]) -> float | None:
    relevant = {pmid for pmid, relevance in gold.items() if relevance > 0}
    nonrelevant = {pmid for pmid, relevance in gold.items() if relevance == 0}
    denominator = min(len(relevant), len(nonrelevant))
    if not relevant or denominator == 0:
        return None

    nonrelevant_seen = 0
    score = 0.0
    for pmid in ranked_pmids:
        if pmid in nonrelevant:
            nonrelevant_seen += 1
        elif pmid in relevant:
            score += 1 - min(nonrelevant_seen, denominator) / denominator
    return score / len(relevant)


def score_retrieval(qrels: list[dict[str, str]], runs: list[dict[str, str]]) -> dict[str, Any]:
    relevance_by_question: dict[str, dict[str, float]] = defaultdict(dict)
    for row in qrels:
        relevance_by_question[row["question_id"]][row["pmid"]] = _as_float(row.get("relevance"))

    runs_by_system_question: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in runs:
        runs_by_system_question[(row["system"], row["question_id"])].append(row)

    per_system: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "precision_at_5": [],
            "recall_at_10": [],
            "ndcg_at_10": [],
            "judged_at_10": [],
            "unjudged_at_10": [],
            "returned_at_10": [],
            "bpref": [],
        }
    )
    per_question: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)

    for (system, question_id), rows in runs_by_system_question.items():
        gold = relevance_by_question.get(question_id, {})
        if not gold:
            continue
        ranked = sorted(rows, key=lambda row: int(row.get("rank") or 0))
        top5 = ranked[:5]
        top10 = ranked[:10]

        relevant_top5 = sum(1 for row in top5 if gold.get(row["pmid"], 0) > 0)
        relevant_top10 = sum(1 for row in top10 if gold.get(row["pmid"], 0) > 0)
        total_relevant = sum(1 for rel in gold.values() if rel > 0)
        observed_rels = [gold.get(row["pmid"], 0.0) for row in top10]
        ideal_rels = sorted(gold.values(), reverse=True)[:10]
        ideal_dcg = _dcg(ideal_rels)
        judged_top10 = sum(1 for row in top10 if row["pmid"] in gold)
        returned = len(top10)

        question_metrics = {
            "precision_at_5": relevant_top5 / 5,
            "recall_at_10": relevant_top10 / total_relevant if total_relevant else 0.0,
            "ndcg_at_10": _dcg(observed_rels) / ideal_dcg if ideal_dcg else 0.0,
        }
        per_question[system][question_id] = question_metrics
        for metric, value in question_metrics.items():
            per_system[system][metric].append(value)
        per_system[system]["judged_at_10"].append(
            judged_top10 / returned if returned else 0.0
        )
        per_system[system]["unjudged_at_10"].append(
            (returned - judged_top10) / returned if returned else 0.0
        )
        per_system[system]["returned_at_10"].append(returned / 10)
        bpref = _bpref([row["pmid"] for row in ranked], gold)
        if bpref is not None:
            per_system[system]["bpref"].append(bpref)

    summary = {}
    for system, metrics in sorted(per_system.items()):
        summary[system] = {
            metric: _mean(values) for metric, values in metrics.items()
        }
        summary[system]["question_count"] = len(per_question[system])
        summary[system]["bpref_evaluable_questions"] = len(metrics["bpref"])

    systems = sorted(per_question)
    if len(systems) == 2:
        shared_questions = sorted(set(per_question[systems[0]]) & set(per_question[systems[1]]))
        comparisons: dict[str, Any] = {
            "systems": systems,
            "diff_direction": f"{systems[0]} minus {systems[1]}",
            "n_questions": len(shared_questions),
            "metrics": {},
        }
        for metric in ["precision_at_5", "recall_at_10", "ndcg_at_10"]:
            diffs = [
                per_question[systems[0]][question_id][metric]
                - per_question[systems[1]][question_id][metric]
                for question_id in shared_questions
            ]
            point, lo, hi = _bootstrap_mean_ci(diffs)
            comparisons["metrics"][metric] = {
                "mean_diff": point,
                "bootstrap_95ci": [lo, hi],
                "sign_test_p": _sign_test_p_value(diffs),
                "wins_first_system": sum(1 for diff in diffs if diff > 1e-9),
                "wins_second_system": sum(1 for diff in diffs if diff < -1e-9),
                "ties": sum(1 for diff in diffs if abs(diff) <= 1e-9),
            }
        summary["_paired_comparison"] = comparisons
    return summary


def score_claims(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(str(row.get("support_label", "")).strip().lower())

    summary = {}
    for system, labels in sorted(grouped.items()):
        total = len(labels)
        direct = labels.count("direct")
        partial = labels.count("partial")
        unsupported = labels.count("unsupported")
        summary[system] = {
            "claim_count": total,
            "citation_support_rate": round(direct / total, 4) if total else None,
            "lenient_support_rate": round((direct + 0.5 * partial) / total, 4) if total else None,
            "hallucination_rate": round(unsupported / total, 4) if total else None,
        }
    return summary


def _question_id_from_edge_id(edge_id: str) -> str:
    """edge_id is formatted "Q0NN-E0M" -- the question_id prefix before the last '-'."""
    return edge_id.rsplit("-", 1)[0]


def _two_rater_paired_values(
    rows: list[dict[str, str]], id_field: str, field: str
) -> tuple[list[str], list[int], list[int]] | None:
    """Align two raters' values for `field`, one pair per distinct `id_field` value present under
    both raters. Returns None unless the data has exactly two distinct rater_id values -- kappa
    between more or fewer than two raters isn't the pairwise statistic this computes.
    """
    raters = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
    if len(raters) != 2:
        return None
    by_item_rater = {
        (row[id_field], row["rater_id"]): row for row in rows if row.get(id_field)
    }
    item_ids = sorted({row[id_field] for row in rows if row.get(id_field)})

    ids, a_vals, b_vals = [], [], []
    for item_id in item_ids:
        a = by_item_rater.get((item_id, raters[0]))
        b = by_item_rater.get((item_id, raters[1]))
        if a is None or b is None:
            continue
        ids.append(item_id)
        a_vals.append(int(round(_as_float(a.get(field)))))
        b_vals.append(int(round(_as_float(b.get(field)))))
    return ids, a_vals, b_vals


def score_edge_ratings(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(row)

    summary = {}
    for system, items in sorted(grouped.items()):
        total = len(items)
        meaningful = sum(1 for row in items if _as_bool(row.get("biologically_meaningful")))
        relation_correct = sum(1 for row in items if _as_bool(row.get("relation_type_correct")))

        by_question: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in items:
            by_question[_question_id_from_edge_id(row["edge_id"])].append(row)
        bio_by_q = [
            mean(1.0 if _as_bool(r.get("biologically_meaningful")) else 0.0 for r in q_rows)
            for q_rows in by_question.values()
        ]
        rel_by_q = [
            mean(1.0 if _as_bool(r.get("relation_type_correct")) else 0.0 for r in q_rows)
            for q_rows in by_question.values()
        ]
        bio_point, bio_lo, bio_hi = _bootstrap_mean_ci(bio_by_q) if bio_by_q else (None, None, None)
        rel_point, rel_lo, rel_hi = _bootstrap_mean_ci(rel_by_q) if rel_by_q else (None, None, None)

        summary[system] = {
            "edge_count": total,
            "biological_precision": round(meaningful / total, 4) if total else None,
            "biological_precision_95ci": [bio_lo, bio_hi],
            "relation_type_precision": round(relation_correct / total, 4) if total else None,
            "relation_type_precision_95ci": [rel_lo, rel_hi],
        }

    for field, label in (
        ("biologically_meaningful", "biologically_meaningful"),
        ("relation_type_correct", "relation_type_correct"),
    ):
        aligned = _two_rater_paired_values(rows, "edge_id", field)
        if aligned is None:
            continue
        _ids, a_vals, b_vals = aligned
        summary.setdefault("_inter_rater_agreement", {"raters": None, "kappa": {}})
        raters = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
        summary["_inter_rater_agreement"]["raters"] = raters
        summary["_inter_rater_agreement"]["n_paired_edges"] = len(a_vals)
        summary["_inter_rater_agreement"]["kappa"][label] = cohens_kappa(a_vals, b_vals)

    raters = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
    if len(raters) >= 3:
        agreement = summary.setdefault(
            "_inter_rater_agreement", {"raters": raters, "kappa": {}}
        )
        agreement["raters"] = raters
        agreement.setdefault("fleiss_kappa", {})
        agreement.setdefault("krippendorff_alpha", {})
        for field, label in (
            ("biologically_meaningful", "biologically_meaningful"),
            ("relation_type_correct", "relation_type_correct"),
        ):
            item_ids, values, _raters = _multi_rater_values(rows, "edge_id", field)
            agreement["n_multi_rated_edges"] = len(item_ids)
            agreement["fleiss_kappa"][label] = fleiss_kappa(values)
            agreement["krippendorff_alpha"][label] = krippendorff_alpha(
                values, level="nominal"
            )

    return summary


def score_path_qrels(
    qrels: list[dict[str, str]], runs: list[dict[str, str]]
) -> dict[str, Any]:
    """Score path-level qrels for mechanism / 2-hop evaluation."""

    gold_by_question: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in qrels:
        gold_by_question[row["question_id"]].append(row)

    runs_by_system_question: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in runs:
        runs_by_system_question[(row["system"], row["question_id"])].append(row)

    summary: dict[str, Any] = {}
    systems = sorted({system for system, _ in runs_by_system_question})
    for system in systems:
        per_question: dict[str, list[float]] = defaultdict(list)
        question_ids = sorted(
            set(gold_by_question) | {qid for sys, qid in runs_by_system_question if sys == system}
        )
        for question_id in question_ids:
            gold_rows = gold_by_question.get(question_id, [])
            pred_rows = sorted(
                runs_by_system_question.get((system, question_id), []),
                key=lambda row: int(row.get("path_rank") or row.get("rank") or 0),
            )
            if not gold_rows and not pred_rows:
                continue

            positive_gold = [
                row
                for row in gold_rows
                if _as_float(row.get("relevance") or row.get("path_relevance"), 0.0) > 0
                and not _as_bool(row.get("is_negative_control"))
            ]
            negative_control = bool(
                gold_rows
                and all(
                    _as_bool(row.get("is_negative_control"))
                    or _as_float(row.get("relevance") or row.get("path_relevance"), 0.0) <= 0
                    for row in gold_rows
                )
            )

            gold_exact = {
                _path_signature(row)
                for row in positive_gold
                if int(round(_as_float(row.get("relevance") or row.get("path_relevance"), 0.0)))
                >= 2
            }
            gold_partial = {_path_signature(row) for row in positive_gold}
            gold_bridge = {
                str(row.get("bridge", "")).strip()
                for row in positive_gold
                if row.get("bridge")
            }
            gold_pmids = {_path_signature(row): _path_pmids(row) for row in positive_gold}
            gold_by_relaxed: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
            for row in positive_gold:
                gold_by_relaxed[
                    (
                        str(row.get("source", "")).strip(),
                        str(row.get("bridge", "")).strip(),
                        str(row.get("target", "")).strip(),
                    )
                ].append(row)

            top_k = pred_rows[:5]
            pred_exact = {_path_signature(row) for row in top_k}
            pred_relaxed = {
                (
                    str(row.get("source", "")).strip(),
                    str(row.get("bridge", "")).strip(),
                    str(row.get("target", "")).strip(),
                )
                for row in top_k
            }
            pred_bridge = {
                str(row.get("bridge", "")).strip()
                for row in top_k
                if row.get("bridge")
            }

            exact_hits = len(pred_exact & gold_exact)
            relaxed_hits = len(pred_relaxed & gold_partial)
            predicted_count = len(top_k)
            supported_question = 1.0 if relaxed_hits > 0 else 0.0
            exact_question = 1.0 if exact_hits > 0 else 0.0
            negative_fp = 1.0 if negative_control and predicted_count > 0 else 0.0
            top1_supported = 1.0 if (top_k and _path_signature(top_k[0]) in gold_exact) else 0.0
            support_gain = supported_question - top1_supported

            per_question["supported_path_precision_at_5"].append(
                round(relaxed_hits / predicted_count, 4) if predicted_count else 0.0
            )
            per_question["exact_path_precision_at_5"].append(
                round(exact_hits / predicted_count, 4) if predicted_count else 0.0
            )
            per_question["supported_path_recall"].append(supported_question)
            per_question["exact_path_recall"].append(
                round(exact_hits / len(gold_exact), 4) if gold_exact else 0.0
            )
            per_question["partial_path_recall"].append(
                round(relaxed_hits / len(gold_partial), 4) if gold_partial else 0.0
            )
            per_question["negative_control_false_positive_rate"].append(negative_fp)
            per_question["supported_discovery_gain_at_5"].append(support_gain)

            bridge_precision = (
                round(len(pred_bridge & gold_bridge) / len(pred_bridge), 4)
                if pred_bridge
                else 0.0
            )
            bridge_recall = (
                round(len(pred_bridge & gold_bridge) / len(gold_bridge), 4)
                if gold_bridge
                else 0.0
            )
            bridge_f1 = (
                round(2 * bridge_precision * bridge_recall / (bridge_precision + bridge_recall), 4)
                if bridge_precision + bridge_recall
                else 0.0
            )
            per_question["bridge_entity_precision"].append(bridge_precision)
            per_question["bridge_entity_recall"].append(bridge_recall)
            per_question["bridge_entity_f1"].append(bridge_f1)

            direction_correct = 0
            relation_correct = 0
            matched_paths = 0
            evidence_fraction: list[float] = []
            cross_doc_count = 0
            for row in top_k:
                relaxed_key = (
                    str(row.get("source", "")).strip(),
                    str(row.get("bridge", "")).strip(),
                    str(row.get("target", "")).strip(),
                )
                gold_candidates = gold_by_relaxed.get(relaxed_key, [])
                if not gold_candidates:
                    continue
                matched_paths += 1
                pred_relations = (
                    str(row.get("relation_1", "")).strip().lower(),
                    str(row.get("relation_2", "")).strip().lower(),
                )
                pred_directions = (
                    str(row.get("direction_1", "")).strip().lower(),
                    str(row.get("direction_2", "")).strip().lower(),
                )
                pred_pmids = _path_pmids(row)
                if len(pred_pmids) >= 2:
                    cross_doc_count += 1
                best_relation = False
                best_direction = False
                best_overlap = 0.0
                for gold_row in gold_candidates:
                    gold_relations = (
                        str(gold_row.get("relation_1", "")).strip().lower(),
                        str(gold_row.get("relation_2", "")).strip().lower(),
                    )
                    gold_directions = (
                        str(gold_row.get("direction_1", "")).strip().lower(),
                        str(gold_row.get("direction_2", "")).strip().lower(),
                    )
                    gold_pmid_set = gold_pmids.get(_path_signature(gold_row), set())
                    if pred_relations == gold_relations:
                        best_relation = True
                    if pred_directions == gold_directions:
                        best_direction = True
                    if gold_pmid_set:
                        best_overlap = max(
                            best_overlap,
                            len(pred_pmids & gold_pmid_set) / len(gold_pmid_set),
                        )
                relation_correct += 1 if best_relation else 0
                direction_correct += 1 if best_direction else 0
                evidence_fraction.append(best_overlap)

            per_question["relation_alignment_rate"].append(
                round(relation_correct / matched_paths, 4) if matched_paths else 0.0
            )
            per_question["direction_accuracy"].append(
                round(direction_correct / matched_paths, 4) if matched_paths else 0.0
            )
            per_question["evidence_completeness"].append(
                round(mean(evidence_fraction), 4) if evidence_fraction else 0.0
            )
            per_question["cross_document_synthesis_rate"].append(
                round(cross_doc_count / predicted_count, 4) if predicted_count else 0.0
            )

        summary[system] = {metric: _mean(values) for metric, values in per_question.items()}
        summary[system]["question_count"] = len(question_ids)

    return summary


def score_mean_ratings(rows: list[dict[str, str]], fields: list[str]) -> dict[str, Any]:
    # Per-rating item identifier for pairing the two raters' judgments: hypothesis_ratings.csv has
    # hypothesis_id, edge_ratings-shaped inputs have edge_id, answer_ratings.csv (one rating per
    # question per rater, no finer-grained ID) falls back to question_id.
    if rows and "hypothesis_id" in rows[0]:
        id_field = "hypothesis_id"
    elif rows and "edge_id" in rows[0]:
        id_field = "edge_id"
    else:
        id_field = "question_id"

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        system = row["system"]
        for field in fields:
            grouped[system][field].append(_as_float(row.get(field)))

    summary = {}
    for system, values_by_field in sorted(grouped.items()):
        field_means = {field: _mean(values) for field, values in values_by_field.items()}
        available = [value for value in field_means.values() if value is not None]
        field_means["overall_mean"] = round(mean(available), 4) if available else None
        summary[system] = field_means

    # Inter-rater agreement: quadratic-weighted kappa, appropriate for ordinal 1-5 scores (a
    # 3-vs-4 disagreement is penalized far less than a 1-vs-5 disagreement).
    kappas: dict[str, float | None] = {}
    raters_used = None
    n_paired = None
    for field in fields:
        aligned = _two_rater_paired_values(rows, id_field, field)
        if aligned is None:
            continue
        _ids, a_vals, b_vals = aligned
        kappas[field] = cohens_kappa(a_vals, b_vals, weighted="quadratic")
        raters_used = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
        n_paired = len(a_vals)
    if kappas:
        summary["_inter_rater_agreement"] = {
            "raters": raters_used,
            "n_paired_items": n_paired,
            "weighted_kappa": kappas,
        }

    raters = sorted({row.get("rater_id", "") for row in rows if row.get("rater_id")})
    if len(raters) >= 3:
        multi = summary.setdefault("_inter_rater_agreement", {})
        multi["raters"] = raters
        multi.setdefault("fleiss_kappa", {})
        multi.setdefault("krippendorff_alpha", {})
        for field in fields:
            item_ids, values, _raters = _multi_rater_values(rows, id_field, field)
            multi["n_multi_rated_items"] = len(item_ids)
            multi["fleiss_kappa"][field] = fleiss_kappa(values)
            multi["krippendorff_alpha"][field] = krippendorff_alpha(
                values, level="ordinal"
            )

    # Paired per-question comparison, only meaningful with exactly two systems (e.g.
    # netmedex_hybrid_rag vs traditional_rag) -- averages across raters within each
    # system+question first, so a rater with more rows never gets implicit extra weight.
    systems = sorted(summary.keys() - {"_inter_rater_agreement"})
    if len(systems) == 2:
        per_question_system: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in rows:
            per_q_score = mean(_as_float(row.get(f)) for f in fields)
            per_question_system[(row["question_id"], row["system"])].append(per_q_score)

        question_ids = sorted({q for q, _ in per_question_system})
        diffs = []
        for qid in question_ids:
            a_scores = per_question_system.get((qid, systems[0]))
            b_scores = per_question_system.get((qid, systems[1]))
            if not a_scores or not b_scores:
                continue
            diffs.append(mean(a_scores) - mean(b_scores))

        if diffs:
            point, lo, hi = _bootstrap_mean_ci(diffs)
            summary["_paired_comparison"] = {
                "systems": systems,
                "diff_direction": f"{systems[0]} minus {systems[1]}",
                "n_questions": len(diffs),
                "mean_diff": point,
                "bootstrap_95ci": [lo, hi],
                "sign_test_p": _sign_test_p_value(diffs),
                "wins_first_system": sum(1 for d in diffs if d > 1e-9),
                "wins_second_system": sum(1 for d in diffs if d < -1e-9),
                "ties": sum(1 for d in diffs if abs(d) <= 1e-9),
            }

    return summary


def score_edge_verification_delta(
    baseline_rows: list[dict[str, str]], verified_rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Paired comparison between two edge_ratings.csv-shaped inputs.

    If the two inputs share the same edge set, pair on `edge_id` directly so the verifier audit
    is edge-stable. Otherwise fall back to question-level pairing on the question_id prefix of
    `edge_id`, which is appropriate for independent extraction runs that do not yield identical
    edge IDs.
    """

    def per_question_precision(rows: list[dict[str, str]], field: str) -> dict[str, float]:
        by_q: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            qid = _question_id_from_edge_id(row["edge_id"])
            by_q[qid].append(1.0 if _as_bool(row.get(field)) else 0.0)
        return {qid: mean(vals) for qid, vals in by_q.items()}

    def per_edge_precision(rows: list[dict[str, str]], field: str) -> dict[str, float]:
        by_edge: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            edge_id = row.get("edge_id")
            if not edge_id:
                continue
            by_edge[edge_id].append(1.0 if _as_bool(row.get(field)) else 0.0)
        return {edge_id: mean(vals) for edge_id, vals in by_edge.items()}

    result: dict[str, Any] = {}
    for field, label in (
        ("biologically_meaningful", "biological_precision"),
        ("relation_type_correct", "relation_type_precision"),
    ):
        baseline_by_edge = per_edge_precision(baseline_rows, field)
        verified_by_edge = per_edge_precision(verified_rows, field)
        shared_edge_ids = sorted(set(baseline_by_edge) & set(verified_by_edge))
        pair_mode = "edge_id" if shared_edge_ids and len(shared_edge_ids) >= min(
            len(baseline_by_edge), len(verified_by_edge)
        ) * 0.8 else "question_id"

        if pair_mode == "edge_id":
            diffs = [verified_by_edge[eid] - baseline_by_edge[eid] for eid in shared_edge_ids]
            baseline_only = sorted(set(baseline_by_edge) - set(verified_by_edge))
            verified_only = sorted(set(verified_by_edge) - set(baseline_by_edge))
            shared_count = len(diffs)
        else:
            baseline_by_q = per_question_precision(baseline_rows, field)
            verified_by_q = per_question_precision(verified_rows, field)
            shared_qids = sorted(set(baseline_by_q) & set(verified_by_q))
            diffs = [verified_by_q[q] - baseline_by_q[q] for q in shared_qids]
            baseline_only = sorted(set(baseline_by_q) - set(verified_by_q))
            verified_only = sorted(set(verified_by_q) - set(baseline_by_q))
            shared_count = len(diffs)
        if not diffs:
            result[label] = None
            continue
        point, lo, hi = _bootstrap_mean_ci(diffs)
        result[label] = {
            "pairing_mode": pair_mode,
            "n_shared_items": shared_count,
            "n_shared_questions": shared_count,
            "baseline_only_items": baseline_only,
            "verified_only_items": verified_only,
            "baseline_only_questions": baseline_only,
            "verified_only_questions": verified_only,
            "mean_diff_verified_minus_baseline": point,
            "bootstrap_95ci": [lo, hi],
            "sign_test_p": _sign_test_p_value(diffs),
        }
    return result


def score_arm_exposures(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize whether ablation arms truly expose different evidence sets."""

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        arm = row.get("arm") or row.get("profile") or row.get("system")
        if arm:
            grouped[str(arm)].append(row)

    summary: dict[str, Any] = {}
    arm_question_sets: dict[str, dict[str, dict[str, set[str] | str]]] = {}
    for arm, items in sorted(grouped.items()):
        by_question: dict[str, dict[str, set[str] | str]] = {}
        for row in items:
            qid = row.get("question_id")
            if not qid:
                continue
            by_question[qid] = {
                "pmids": _path_pmids(row),
                "edges": set(_split_values(row.get("exposed_edges"))),
                "paths": set(_split_values(row.get("exposed_paths"))),
                "signature": str(row.get("exposure_signature", "")).strip(),
            }
        arm_question_sets[arm] = by_question
        pmid_counts = [len(meta["pmids"]) for meta in by_question.values()]
        edge_counts = [len(meta["edges"]) for meta in by_question.values()]
        path_counts = [len(meta["paths"]) for meta in by_question.values()]
        summary[arm] = {
            "question_count": len(by_question),
            "median_exposed_pmids": _median(pmid_counts),
            "median_exposed_edges": _median(edge_counts),
            "median_exposed_paths": _median(path_counts),
            "unique_exposure_signatures": len(
                {str(meta["signature"]) for meta in by_question.values() if meta["signature"]}
            ),
        }

    pairwise: dict[str, Any] = {}
    arms = sorted(arm_question_sets)
    for i, arm_a in enumerate(arms):
        for arm_b in arms[i + 1 :]:
            qids = sorted(set(arm_question_sets[arm_a]) & set(arm_question_sets[arm_b]))
            pmid_jaccards = []
            edge_jaccards = []
            path_jaccards = []
            signature_matches = 0
            for qid in qids:
                a = arm_question_sets[arm_a][qid]
                b = arm_question_sets[arm_b][qid]
                j = _jaccard(set(a["pmids"]), set(b["pmids"]))  # type: ignore[arg-type]
                if j is not None:
                    pmid_jaccards.append(j)
                j = _jaccard(set(a["edges"]), set(b["edges"]))  # type: ignore[arg-type]
                if j is not None:
                    edge_jaccards.append(j)
                j = _jaccard(set(a["paths"]), set(b["paths"]))  # type: ignore[arg-type]
                if j is not None:
                    path_jaccards.append(j)
                if a["signature"] and a["signature"] == b["signature"]:
                    signature_matches += 1
            pairwise[f"{arm_a}__vs__{arm_b}"] = {
                "n_shared_questions": len(qids),
                "pmid_jaccard_mean": _mean(pmid_jaccards),
                "edge_jaccard_mean": _mean(edge_jaccards),
                "path_jaccard_mean": _mean(path_jaccards),
                "signature_match_rate": round(signature_matches / len(qids), 4) if qids else None,
            }

    if pairwise:
        summary["_pairwise_overlap"] = pairwise
    return summary


def score_efficiency(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(row)

    summary = {}
    medians = {}
    for system, items in sorted(grouped.items()):
        times = [_as_float(row.get("elapsed_minutes")) for row in items]
        completed = sum(1 for row in items if _as_bool(row.get("completed")))
        med = _median(times)
        medians[system] = med
        summary[system] = {
            "task_count": len(items),
            "median_elapsed_minutes": med,
            "mean_elapsed_minutes": _mean(times),
            "completion_rate": round(completed / len(items), 4) if items else None,
        }

    manual = medians.get("manual_pubmed")
    for system, med in medians.items():
        if system != "manual_pubmed" and manual and med is not None:
            summary[system]["time_saved_vs_manual"] = round((manual - med) / manual, 4)
    return summary


def score_performance(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(row)

    summary = {}
    for system, items in sorted(grouped.items()):
        build = [_as_float(row.get("build_seconds")) for row in items]
        index = [_as_float(row.get("index_seconds")) for row in items]
        query = [_as_float(row.get("query_seconds")) for row in items]
        failures = sum(1 for row in items if not _as_bool(row.get("success")))
        summary[system] = {
            "run_count": len(items),
            "build_seconds_median": _median(build),
            "build_seconds_p90": _p90(build),
            "index_seconds_median": _median(index),
            "query_seconds_median": _median(query),
            "query_seconds_p90": _p90(query),
            "failure_rate": round(failures / len(items), 4) if items else None,
        }
    return summary


def _sus_score(row: dict[str, str]) -> float:
    total = 0.0
    for i in range(1, 11):
        value = _as_float(row.get(f"sus_q{i}"))
        total += value - 1 if i % 2 == 1 else 5 - value
    return total * 2.5


def score_user_survey(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(row)

    summary = {}
    for system, items in sorted(grouped.items()):
        summary[system] = {
            "respondent_count": len(items),
            "sus_mean": _mean([_sus_score(row) for row in items]),
            "ease_of_use_mean": _mean([_as_float(row.get("ease_of_use")) for row in items]),
            "trust_mean": _mean([_as_float(row.get("trust")) for row in items]),
            "intent_to_continue_mean": _mean(
                [_as_float(row.get("intent_to_continue")) for row in items]
            ),
        }
    return summary


def build_summary(
    input_dir: Path,
    qrels_path: Path | None = None,
    edge_ratings_verified_path: Path | None = None,
) -> dict[str, Any]:
    files = {
        "qrels": _read_csv(qrels_path or input_dir / "qrels.csv"),
        "retrieval_runs": _read_csv(input_dir / "retrieval_runs.csv"),
        "path_qrels": _read_csv(input_dir / "path_qrels.csv"),
        "path_runs": _read_csv(input_dir / "path_runs.csv"),
        "arm_exposures": _read_csv(input_dir / "arm_exposures.csv"),
        "claims": _read_csv(input_dir / "claims.csv"),
        "edge_ratings": _read_csv(input_dir / "edge_ratings.csv"),
        "answer_ratings": _read_csv(input_dir / "answer_ratings.csv"),
        "hypothesis_ratings": _read_csv(input_dir / "hypothesis_ratings.csv"),
        "task_times": _read_csv(input_dir / "task_times.csv"),
        "performance_logs": _read_csv(input_dir / "performance_logs.csv"),
        "user_survey": _read_csv(input_dir / "user_survey.csv"),
    }
    summary: dict[str, Any] = {"input_dir": str(input_dir), "metrics": {}}

    if files["qrels"] and files["retrieval_runs"]:
        summary["metrics"]["retrieval"] = score_retrieval(files["qrels"], files["retrieval_runs"])
    if files["path_qrels"] and files["path_runs"]:
        summary["metrics"]["path_retrieval"] = score_path_qrels(
            files["path_qrels"], files["path_runs"]
        )
    if files["arm_exposures"]:
        summary["metrics"]["arm_exposures"] = score_arm_exposures(files["arm_exposures"])
    if files["claims"]:
        summary["metrics"]["claims"] = score_claims(files["claims"])
    if files["edge_ratings"]:
        summary["metrics"]["relation_quality"] = score_edge_ratings(files["edge_ratings"])
    if files["answer_ratings"]:
        summary["metrics"]["answer_quality"] = score_mean_ratings(
            files["answer_ratings"], ["correctness", "completeness", "relevance"]
        )
    if files["hypothesis_ratings"]:
        summary["metrics"]["hypothesis_value"] = score_mean_ratings(
            files["hypothesis_ratings"],
            ["novelty", "plausibility", "testability", "research_value"],
        )
    if files["task_times"]:
        summary["metrics"]["efficiency"] = score_efficiency(files["task_times"])
    if files["performance_logs"]:
        summary["metrics"]["performance"] = score_performance(files["performance_logs"])
    if files["user_survey"]:
        summary["metrics"]["user_acceptance"] = score_user_survey(files["user_survey"])

    if files["edge_ratings"] and edge_ratings_verified_path:
        verified_rows = _read_csv(edge_ratings_verified_path)
        if verified_rows:
            summary["metrics"]["edge_verification_delta"] = score_edge_verification_delta(
                files["edge_ratings"], verified_rows
            )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Score NetMedEx evaluation CSV files.")
    parser.add_argument("--input-dir", type=Path, default=Path("evaluation/sample_results"))
    parser.add_argument(
        "--qrels",
        type=Path,
        help="Optional frozen qrels file when scoring a separate run directory.",
    )
    parser.add_argument(
        "--edge-ratings-verified",
        type=Path,
        help="Optional edge_ratings.csv-shaped file from a second pipeline configuration "
        "(e.g. with verify_relations enabled) -- adds a paired per-question "
        "edge_verification_delta comparison against --input-dir's edge_ratings.csv.",
    )
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    summary = build_summary(args.input_dir, args.qrels, args.edge_ratings_verified)
    payload = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
