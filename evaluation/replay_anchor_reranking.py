#!/usr/bin/env python3
"""Token-free query-anchor reranking of an existing frozen graph exposure."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean

import networkx as nx

from netmedex.claim_verifier import verify_answer_graph_claims
from netmedex.graph_rag import GraphRetriever


DEFAULT_INPUT = Path("evaluation/formal/runs/adaptive-replay-small-gpt41/questions")
DEFAULT_OUTPUT = Path("evaluation/formal/runs/adaptive-replay-small-anchor-offline")


def build_frozen_graph(paths: list[dict]) -> nx.Graph:
    """Reconstruct only the nodes/edges present in the frozen path exposure."""
    graph = nx.Graph()
    for path in paths:
        node_ids = path.get("node_ids", [])
        names = path.get("names", [])
        for node_id, name in zip(node_ids, names):
            graph.add_node(node_id, name=name, type="entity")
        relations = path.get("relations", [])
        pmid_groups = path.get("edge_pmids", [])
        quote_groups = path.get("edge_evidence_quotes", [])
        for index in range(max(0, len(node_ids) - 1)):
            relation = relations[index] if index < len(relations) else "associated_with"
            pmids = pmid_groups[index] if index < len(pmid_groups) else []
            quotes = quote_groups[index] if index < len(quote_groups) else []
            if not pmids:
                pmids = [f"frozen-hop-{index + 1}"]
            relation_map = {str(pmid): {relation} for pmid in pmids}
            evidence_map = {
                str(pmid): {
                    relation: quotes[min(pmid_index, len(quotes) - 1)] if quotes else ""
                }
                for pmid_index, pmid in enumerate(pmids)
            }
            graph.add_edge(
                node_ids[index],
                node_ids[index + 1],
                relations=relation_map,
                evidences=evidence_map,
                confidences={},
            )
    return graph


def rerank_question(result: dict) -> tuple[list[dict], dict]:
    paths = list(result.get("graph", {}).get("paths", []))
    answer_audit = verify_answer_graph_claims(
        result.get("answers", {}).get("netmedex_hybrid_rag", ""), paths
    )
    if not paths:
        return [], {
            "question_id": result["question_id"],
            "path_count": 0,
            "changed_positions": 0,
            "top_10_set_changes": 0,
            "mean_anchor_bonus": 0.0,
            "target_aligned_at_5_before": 0,
            "target_aligned_at_5_after": 0,
            "mechanism_aligned_at_5_before": 0,
            "mechanism_aligned_at_5_after": 0,
            "answer_path_citations": answer_audit["path_cited_claim_count"],
        }

    retriever = GraphRetriever(build_frozen_graph(paths))
    anchors = retriever._extract_query_anchors(result.get("question", ""), {})
    before = sorted(paths, key=lambda path: (-float(path.get("score", 0.0)), path["path_id"]))
    before_rank = {path["path_id"]: index + 1 for index, path in enumerate(before)}

    rows = []
    for path in paths:
        bonus, features = retriever._score_path_anchors(path.get("node_ids", []), anchors)
        base_score = float(path.get("score", 0.0))
        rows.append(
            {
                "question_id": result["question_id"],
                "path_id": path["path_id"],
                "names": " -> ".join(path.get("names", [])),
                "base_score": base_score,
                "anchor_bonus": bonus,
                "reranked_score": base_score + bonus,
                "old_rank": before_rank[path["path_id"]],
                "anchor_features": features,
            }
        )
    rows.sort(key=lambda row: (-row["reranked_score"], row["path_id"]))
    for index, row in enumerate(rows):
        row["new_rank"] = index + 1

    before_top_5 = before[:5]
    after_top_5 = rows[:5]
    before_features = {row["path_id"]: row["anchor_features"] for row in rows}

    def count_feature(items, field, features_in_rows=False):
        if features_in_rows:
            return sum(bool(item["anchor_features"].get(field)) for item in items)
        return sum(bool(before_features[item["path_id"]].get(field)) for item in items)

    summary = {
        "question_id": result["question_id"],
        "path_count": len(rows),
        "changed_positions": sum(row["old_rank"] != row["new_rank"] for row in rows),
        "top_10_set_changes": len(
            {path["path_id"] for path in before[:10]} ^ {row["path_id"] for row in rows[:10]}
        ),
        "mean_anchor_bonus": mean(row["anchor_bonus"] for row in rows),
        "target_aligned_at_5_before": count_feature(
            before_top_5, "end_matches_query_focus"
        ),
        "target_aligned_at_5_after": count_feature(
            after_top_5, "end_matches_query_focus", True
        ),
        "mechanism_aligned_at_5_before": count_feature(
            before_top_5, "bridge_matches_mechanism_context"
        ),
        "mechanism_aligned_at_5_after": count_feature(
            after_top_5, "bridge_matches_mechanism_context", True
        ),
        "answer_path_citations": answer_audit["path_cited_claim_count"],
        "source_anchor_ids": sorted(str(value) for value in anchors["source_ids"]),
        "target_anchor_ids": sorted(str(value) for value in anchors["target_ids"]),
        "mechanism_anchor_ids": sorted(str(value) for value in anchors["mechanism_ids"]),
    }
    return rows, summary


def write_outputs(output_dir: Path, rows: list[dict], summaries: list[dict], input_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "question_id",
        "path_id",
        "old_rank",
        "new_rank",
        "names",
        "base_score",
        "anchor_bonus",
        "reranked_score",
        "anchor_features",
    ]
    with (output_dir / "anchor_path_reranking.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = dict(row)
            serializable["anchor_features"] = json.dumps(
                row["anchor_features"], ensure_ascii=False, sort_keys=True
            )
            writer.writerow(serializable)

    payload = {
        "mode": "offline_frozen_exposure_anchor_reranking",
        "llm_api_calls": 0,
        "input_dir": str(input_dir),
        "question_summaries": summaries,
    }
    (output_dir / "anchor_replay_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report_lines = [
        "# Query-Anchor Frozen Replay",
        "",
        f"- Frozen exposure source: `{input_dir}`",
        "- LLM/API calls: 0",
        "- Scope: rerank only the paths already present in each frozen top-20 exposure",
        "- Anchor bonus cap: 0.12",
        "",
        "| Question | Paths | Rank changes | Top-10 Δ | Mean bonus | Target@5 | Path cites |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        report_lines.append(
            f"| {item['question_id']} | {item['path_count']} | {item['changed_positions']} | "
            f"{item['top_10_set_changes']} | {item['mean_anchor_bonus']:.3f} | "
            f"{item['target_aligned_at_5_before']} → {item['target_aligned_at_5_after']} | "
            f"{item['answer_path_citations']} |"
        )
    report_lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This deterministic development replay is not a superiority test.",
            "It measures ordering only inside the already exposed path pool.",
            "It cannot recover omitted candidates or regenerate answers.",
            "The frozen GPT-4.1 answers contain no explicit PATH citations, including the two "
            "questions with graph exposure (Q001 and Q007). This is a citation-compliance failure "
            "for the old run; the new verifier will record it automatically in future results.",
            "",
        ]
    )
    (output_dir / "anchor_replay_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--question-ids", nargs="+", default=["Q001", "Q002", "Q007"])
    args = parser.parse_args()

    all_rows = []
    summaries = []
    for question_id in args.question_ids:
        result_path = args.input_dir / question_id / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rows, summary = rerank_question(result)
        all_rows.extend(rows)
        summaries.append(summary)
    write_outputs(args.output_dir, all_rows, summaries, args.input_dir)


if __name__ == "__main__":
    main()
