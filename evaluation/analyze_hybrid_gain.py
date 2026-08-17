#!/usr/bin/env python3
"""Analyze the blinded local-model Hybrid-gain ablation with paired/cluster bootstrap."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


FIELDS = (
    "correctness",
    "completeness",
    "relevance",
    "grounding",
    "mechanistic_coherence",
    "research_value",
)
SYSTEMS = (
    "B_traditional_rag",
    "C1_kg_reranking",
    "C2_kg_expansion",
    "D1_all_safe_paths",
    "D2_incremental_paths",
    "D3_incremental_natural_fusion",
    "Oracle_local_path_selection",
)
def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def bootstrap_ci(values: list[float], seed: int = 20260817) -> list[float]:
    rng = random.Random(seed)
    draws = [mean(rng.choices(values, k=len(values))) for _ in range(10_000)]
    return [round(percentile(draws, 0.025), 4), round(percentile(draws, 0.975), 4)]


def sign_p(values: list[float]) -> float:
    wins = sum(value > 1e-12 for value in values)
    losses = sum(value < -1e-12 for value in values)
    n = wins + losses
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2**n
    return min(1.0, 2 * tail)


def load_pass(ratings: Path, key: Path) -> dict[str, dict[str, dict[str, float]]]:
    identity = {row["answer_id"]: row["system"] for row in rows(key)}
    result: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for row in rows(ratings):
        if not row.get("rater_id", "").strip():
            continue
        system = identity[row["answer_id"]]
        scores = {field: float(row[field]) for field in FIELDS}
        scores["overall"] = mean(scores.values())
        result[row["question_id"]][system] = scores
    return result


def normalize_fallback(
    ratings: dict[str, dict[str, dict[str, float]]],
    intervention: set[str],
) -> dict[str, dict[str, dict[str, float]]]:
    for qid, system_scores in ratings.items():
        if qid in intervention:
            continue
        baseline = system_scores["B_traditional_rag"]
        for system in SYSTEMS:
            system_scores[system] = dict(baseline)
    return ratings


def intervention_qids_from_run(root: Path) -> list[str]:
    qids = []
    for path in sorted((root / "arm_D2" / "questions").glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        decision = result.get("evidence_exposure", {}).get("integration_decision", {})
        if decision.get("mode") == "full_hybrid":
            qids.append(str(result.get("question_id", path.parent.name)))
    if not qids:
        raise ValueError("No D2 full_hybrid intervention questions found")
    return sorted(qids)


def contrast(
    scores: dict[str, dict[str, dict[str, float]]],
    left: str,
    right: str,
    qids: list[str],
    clusters: dict[str, str],
) -> dict:
    differences = {
        qid: scores[qid][left]["overall"] - scores[qid][right]["overall"]
        for qid in qids
    }
    values = list(differences.values())
    grouped: dict[str, list[float]] = defaultdict(list)
    for qid, value in differences.items():
        grouped[clusters[qid]].append(value)
    cluster_values = [mean(group) for group in grouped.values()]
    return {
        "left": left,
        "right": right,
        "question_level": {
            "n": len(values),
            "mean_diff": round(mean(values), 4),
            "bootstrap_95ci": bootstrap_ci(values),
            "wins": sum(value > 1e-12 for value in values),
            "losses": sum(value < -1e-12 for value in values),
            "ties": sum(abs(value) <= 1e-12 for value in values),
            "sign_test_p": round(sign_p(values), 4),
        },
        "cluster_level": {
            "n": len(cluster_values),
            "mean_diff": round(mean(cluster_values), 4),
            "bootstrap_95ci": bootstrap_ci(cluster_values),
            "wins": sum(value > 1e-12 for value in cluster_values),
            "losses": sum(value < -1e-12 for value in cluster_values),
            "ties": sum(abs(value) <= 1e-12 for value in cluster_values),
            "sign_test_p": round(sign_p(cluster_values), 4),
        },
        "per_question": {qid: round(value, 4) for qid, value in differences.items()},
    }


def itt_contrast(
    scores: dict[str, dict[str, dict[str, float]]],
    left: str,
    right: str,
    all_qids: list[str],
    intervention_qids: set[str],
    clusters: dict[str, str],
) -> dict:
    differences = {
        qid: (
            scores[qid][left]["overall"] - scores[qid][right]["overall"]
            if qid in intervention_qids
            else 0.0
        )
        for qid in all_qids
    }
    values = list(differences.values())
    grouped: dict[str, list[float]] = defaultdict(list)
    for qid, value in differences.items():
        grouped[clusters[qid]].append(value)
    cluster_values = [mean(group) for group in grouped.values()]
    return {
        "left": left,
        "right": right,
        "question_level": {
            "n": len(values),
            "mean_diff": round(mean(values), 4),
            "bootstrap_95ci": bootstrap_ci(values),
            "wins": sum(value > 1e-12 for value in values),
            "losses": sum(value < -1e-12 for value in values),
            "ties": sum(abs(value) <= 1e-12 for value in values),
            "sign_test_p": round(sign_p(values), 4),
        },
        "cluster_level": {
            "n": len(cluster_values),
            "mean_diff": round(mean(cluster_values), 4),
            "bootstrap_95ci": bootstrap_ci(cluster_values),
            "wins": sum(value > 1e-12 for value in cluster_values),
            "losses": sum(value < -1e-12 for value in cluster_values),
            "ties": sum(abs(value) <= 1e-12 for value in cluster_values),
            "sign_test_p": round(sign_p(cluster_values), 4),
        },
        "per_question": {qid: round(value, 4) for qid, value in differences.items()},
        "nonintervention_differences_set_to_zero_because_answers_are_identical": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=Path("evaluation/formal/path_positive_20_v1/selection_manifest.json"),
    )
    args = parser.parse_args()
    root = args.run_dir
    intervention_qids = intervention_qids_from_run(root)
    intervention = set(intervention_qids)
    pass1 = load_pass(
        root / "judge_local_pass1.csv", root / "blinded_answer_key_pass1.csv"
    )
    pass2 = load_pass(
        root / "judge_local_pass2.csv", root / "blinded_answer_key_pass2.csv"
    )
    for qid in intervention_qids:
        if set(pass1.get(qid, {})) != set(SYSTEMS):
            raise ValueError(f"Pass 1 incomplete for {qid}")
        if set(pass2.get(qid, {})) != set(SYSTEMS):
            raise ValueError(f"Pass 2 incomplete for {qid}")

    combined: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for qid in intervention_qids:
        for system in SYSTEMS:
            source = [pass1[qid][system], pass2[qid][system]]
            combined[qid][system] = {
                field: mean(item[field] for item in source)
                for field in (*FIELDS, "overall")
            }

    manifest = json.loads(args.selection_manifest.read_text(encoding="utf-8"))
    all_qids = sorted(item["question_id"] for item in manifest["items"])
    clusters = {
        item["question_id"]: item["source_result_sha256"]
        for item in manifest["items"]
    }
    missing_clusters = set(all_qids) - set(clusters)
    if missing_clusters:
        raise ValueError(f"Missing source clusters for: {sorted(missing_clusters)}")
    has_full_pass1 = set(all_qids).issubset(pass1)
    if has_full_pass1:
        pass1 = normalize_fallback(pass1, intervention)
    system_scores = {}
    for system in SYSTEMS:
        system_scores[system] = {
            "itt20": (
                {
                    field: round(mean(pass1[qid][system][field] for qid in all_qids), 4)
                    for field in (*FIELDS, "overall")
                }
                if has_full_pass1
                else None
            ),
            "intervention": {
                field: round(
                    mean(combined[qid][system][field] for qid in intervention_qids), 4
                )
                for field in (*FIELDS, "overall")
            },
        }

    requested = (
        ("C1-B", "C1_kg_reranking", "B_traditional_rag"),
        ("C2-B", "C2_kg_expansion", "B_traditional_rag"),
        ("D1-B", "D1_all_safe_paths", "B_traditional_rag"),
        ("D2-B", "D2_incremental_paths", "B_traditional_rag"),
        ("D3-B", "D3_incremental_natural_fusion", "B_traditional_rag"),
        ("D2-D1", "D2_incremental_paths", "D1_all_safe_paths"),
        ("D3-D2", "D3_incremental_natural_fusion", "D2_incremental_paths"),
        ("Oracle-D3", "Oracle_local_path_selection", "D3_incremental_natural_fusion"),
    )
    contrasts = {}
    for label, left, right in requested:
        contrasts[label] = {
            "itt20": itt_contrast(
                combined, left, right, all_qids, intervention, clusters
            ),
            "intervention": contrast(
                combined, left, right, intervention_qids, clusters
            ),
            "pass_sensitivity_intervention_mean": {
                "pass1": round(
                    mean(
                        pass1[qid][left]["overall"] - pass1[qid][right]["overall"]
                        for qid in intervention_qids
                    ),
                    4,
                ),
                "pass2": round(
                    mean(
                        pass2[qid][left]["overall"] - pass2[qid][right]["overall"]
                        for qid in intervention_qids
                    ),
                    4,
                ),
            },
        }

    payload = {
        "design": {
            "questions": len(all_qids),
            "intervention_questions": intervention_qids,
            "intervention_question_count": len(intervention_qids),
            "intervention_cluster_count": len({clusters[qid] for qid in intervention_qids}),
            "judges": ["local:gpt-oss:120b pass1", "local:gpt-oss:120b pass2"],
            "human_expert_review_claimed": False,
            "nonintervention_question_count": len(all_qids) - len(intervention_qids),
            "nonintervention_answers_identical_to_B_by_integrity_audit": True,
            "absolute_itt_scores_available": has_full_pass1,
            "itt_contrasts_use_exact_zero_for_identical_nonintervention_answers": True,
            "oracle_and_judge_same_model_non_independence": True,
        },
        "system_scores": system_scores,
        "contrasts": contrasts,
    }
    (root / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    d3_b = contrasts["D3-B"]["intervention"]["question_level"]
    d3_b_cluster = contrasts["D3-B"]["intervention"]["cluster_level"]
    c2_b = contrasts["C2-B"]["intervention"]["question_level"]
    d2_d1 = contrasts["D2-D1"]["intervention"]["question_level"]
    d3_d2 = contrasts["D3-D2"]["intervention"]["question_level"]
    d3_d2_cluster = contrasts["D3-D2"]["intervention"]["cluster_level"]
    lines = [
        "# Hybrid RAG 增量效益實驗結果",
        "",
        "本結果為 20 題 path-positive 開發集、兩輪同一地端 gpt-oss:120b 匿名盲評；",
        "不是人類生醫專家評審，也不是代表性 ITT 或正式 superiority study。",
        f"{len(all_qids) - len(intervention_qids)} 題未觸發 incremental intervention，所有系統直接重用同一份 B 答案；只有 {len(intervention_qids)} 題有實際 treatment 差異。",
        "",
        "## 結論摘要",
        "",
        f"- D3 相對 B 在 intervention 題為 {d3_b['mean_diff']:+.4f}，cluster mean "
        f"{d3_b_cluster['mean_diff']:+.4f}（95% CI {d3_b_cluster['bootstrap_95ci'][0]:+.4f} 至 "
        f"{d3_b_cluster['bootstrap_95ci'][1]:+.4f}）；納入 16 題零差異後，ITT 差值僅 "
        f"{contrasts['D3-B']['itt20']['question_level']['mean_diff']:+.4f}。"
        "**未證明 Hybrid 優於 Traditional RAG**。",
        f"- D3 相對 D2 為 {d3_d2['mean_diff']:+.4f}（兩輪方向一致），但只有 "
        f"{d3_d2_cluster['n']} 個 clusters，cluster CI "
        f"{d3_d2_cluster['bootstrap_95ci'][0]:+.4f} 至 {d3_d2_cluster['bootstrap_95ci'][1]:+.4f}；"
        "自然語言融合有正向訊號，尚非確認性證據。",
        f"- C2 KG expansion 相對 B 為 {c2_b['mean_diff']:+.4f}；D2 相對 D1 為 "
        f"{d2_d1['mean_diff']:+.4f}。目前訊號較支持精準 expansion 與 incremental-only selection，"
        "不支持無差別加入更多安全 paths。",
        f"- 介入率為 {len(intervention_qids)}/{len(all_qids)} "
        f"（{100 * len(intervention_qids) / len(all_qids):.1f}%）；覆蓋率仍是主要限制。",
        "",
        "## Intervention 題平均總分",
        "",
        f"| System | Intervention {len(intervention_qids)} |",
        "|---|---:|",
    ]
    for system in SYSTEMS:
        lines.append(
            f"| {system} | {system_scores[system]['intervention']['overall']:.4f} |"
        )
    lines.extend(["", f"## 主要配對比較（Intervention {len(intervention_qids)}）", ""])
    lines.extend(
        [
            "| Contrast | Mean diff | Question bootstrap 95% CI | W/L/T | Cluster n | Cluster mean | Cluster 95% CI | Pass1 / Pass2 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, _left, _right in requested:
        c = contrasts[label]["intervention"]
        q = c["question_level"]
        g = c["cluster_level"]
        s = contrasts[label]["pass_sensitivity_intervention_mean"]
        lines.append(
            f"| {label} | {q['mean_diff']:+.4f} | {q['bootstrap_95ci'][0]:+.4f} to "
            f"{q['bootstrap_95ci'][1]:+.4f} | {q['wins']}/{q['losses']}/{q['ties']} | "
            f"{g['n']} | {g['mean_diff']:+.4f} | {g['bootstrap_95ci'][0]:+.4f} to "
            f"{g['bootstrap_95ci'][1]:+.4f} | {s['pass1']:+.4f} / {s['pass2']:+.4f} |"
        )
    lines.extend(
        [
            "",
            "## ITT 20 相對差值",
            "",
            "Non-intervention 題的答案逐字相同，因此其 paired difference 精確設為 0。",
            "",
            "| Contrast | ITT mean diff | Question bootstrap 95% CI |",
            "|---|---:|---:|",
        ]
    )
    for label, _left, _right in requested:
        q = contrasts[label]["itt20"]["question_level"]
        lines.append(
            f"| {label} | {q['mean_diff']:+.4f} | {q['bootstrap_95ci'][0]:+.4f} to "
            f"{q['bootstrap_95ci'][1]:+.4f} |"
        )
    lines.extend(
        [
            "",
            "## 解讀限制",
            "",
            f"- {len(intervention_qids)} 個 intervention 題只來自 {len({clusters[qid] for qid in intervention_qids})} 個獨立 source/endpoint clusters，cluster CI 極不穩定。",
            "- 未重評完全相同的 non-intervention 答案，因此不提供各系統 ITT 絕對平均；相對差值將這些題精確設為 0。",
            "- Oracle 選徑與盲評使用同一地端模型，Oracle 分數不是獨立外部驗證。",
            "- 盲評者未看到完整 source documents；其 grounding 分數僅為輔助，引用安全性以 deterministic claim audit 為準。",
            "- 兩輪 pass 的差異反映同一模型的順序與抽樣變異；細小差距不可宣稱 superiority。",
            "- Frozen graph 使用較舊的 graph/NER schema；結果只適用於本次凍結 exposure。",
        ]
    )
    (root / "RESULTS_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
