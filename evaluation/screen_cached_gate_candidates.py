#!/usr/bin/env python3
"""Token-free proxy gate screen over legacy frozen top-path artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import networkx as nx

from netmedex.graph_rag import GraphRetriever


RUNS_DIR = Path("evaluation/formal/runs")
OUTPUT_CSV = Path("evaluation/formal/cached_gate_screen_v1.csv")
OUTPUT_REPORT = Path("evaluation/formal/cached_gate_screen_v1.md")


def reconstruct_graph(paths: list[dict]) -> nx.Graph:
    graph = nx.Graph()
    for path in paths:
        node_ids = path.get("node_ids", [])
        names = path.get("names", [])
        for node_id, name in zip(node_ids, names):
            graph.add_node(node_id, name=name, type="gene")
        for index in range(max(0, len(node_ids) - 1)):
            relation = path.get("relations", [])[index]
            pmids = path.get("edge_pmids", [])[index] or ["legacy"]
            quotes = path.get("edge_evidence_quotes", [])[index] or []
            graph.add_edge(
                node_ids[index],
                node_ids[index + 1],
                relations={str(pmid): {relation} for pmid in pmids},
                evidences={
                    str(pmid): {
                        relation: quotes[min(pmid_index, len(quotes) - 1)] if quotes else ""
                    }
                    for pmid_index, pmid in enumerate(pmids)
                },
                confidences={},
            )
    return graph


def proxy_gate_counts(result: dict) -> Counter:
    paths = result.get("graph", {}).get("paths", [])
    if not paths:
        return Counter()
    retriever = GraphRetriever(reconstruct_graph(paths))
    anchors = retriever._extract_query_anchors(result.get("question", ""), {})
    counts = Counter()
    for path in paths:
        _, features = retriever._score_path_anchors(path.get("node_ids", []), anchors)
        supports = []
        for index, complete in enumerate(path.get("edge_evidence_complete", [])):
            relation = path.get("relations", [])[index]
            directional = path.get("edge_is_directional", [False])[index]
            supports.append(
                {
                    "selected_relation": relation,
                    "selected_pmid": (
                        path.get("edge_pmids", [[]])[index] or [None]
                    )[0],
                    "selected_quote": (
                        path.get("edge_evidence_quotes", [[]])[index] or [None]
                    )[0],
                    "selected_confidence": None,
                    "directional": bool(directional),
                    # Legacy artifacts omitted confidence. Complete PMID+quote
                    # is treated as proxy A only for candidate selection.
                    "support_tier": "A" if complete else "B",
                    "support_reasons": ["legacy_proxy"],
                }
            )
        gate = retriever._classify_path_gate(path.get("node_ids", []), supports, features)
        counts[gate["gate_tier"]] += 1
    return counts


def main() -> None:
    rows = []
    for result_path in sorted(RUNS_DIR.glob("*/questions/*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        paths = result.get("graph", {}).get("paths", [])
        if not paths or any(path.get("gate_tier") for path in paths):
            continue
        counts = proxy_gate_counts(result)
        corpus_path = result_path.with_name("corpus.pubtator")
        literal_none_count = (
            corpus_path.read_text(encoding="utf-8").count("\tNone\t")
            if corpus_path.exists()
            else 0
        )
        question_type = result.get("question_type", "")
        zero_proxy_a = counts["A"] == 0
        run_dir = result_path.parents[2]
        frozen_holdout = (run_dir / "holdout_freeze.json").exists() or (
            "holdout" in run_dir.name
        )
        recommended = not frozen_holdout and zero_proxy_a and question_type in {
            "mechanism",
            "hypothesis",
            "two_hop_path",
            "multilingual_mechanism",
        }
        rows.append(
            {
                "run": result_path.parents[2].name,
                "question_id": result.get("question_id", result_path.parent.name),
                "question_type": question_type,
                "path_count": len(paths),
                "proxy_tier_a": counts["A"],
                "proxy_tier_b": counts["B"],
                "proxy_tier_c": counts["C"],
                "zero_proxy_a": zero_proxy_a,
                "frozen_holdout_excluded": frozen_holdout,
                "literal_none_annotations": literal_none_count,
                "recommended_paid_rescue_test": recommended,
                "question": result.get("question", ""),
                "corpus_path": str(corpus_path) if corpus_path.exists() else "",
            }
        )

    # A question can occur in multiple legacy run directories.  Keep the
    # cleanest and most complete cached artifact so the report represents
    # independent questions rather than run copies.
    deduplicated = {}
    for row in rows:
        key = (row["question_id"], row["question"])
        current = deduplicated.get(key)
        rank = (row["literal_none_annotations"], -row["path_count"], row["run"])
        if current is None:
            deduplicated[key] = row
            continue
        current_rank = (
            current["literal_none_annotations"],
            -current["path_count"],
            current["run"],
        )
        if rank < current_rank:
            deduplicated[key] = row
    rows = list(deduplicated.values())

    rows.sort(
        key=lambda row: (
            not row["recommended_paid_rescue_test"],
            row["proxy_tier_a"],
            -row["path_count"],
            row["question_id"],
        )
    )
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    recommendations = [row for row in rows if row["recommended_paid_rescue_test"]]
    excluded_holdouts = [
        row
        for row in rows
        if row["zero_proxy_a"] and row["frozen_holdout_excluded"]
    ]
    lines = [
        "# Cached Gate Candidate Screen v1",
        "",
        "This is a token-free proxy screen over legacy top-path artifacts. Legacy files omit "
        "confidence, so complete PMID+quote hops are provisionally treated as support Tier A. "
        "The results select paid replay candidates; they are not formal gate outcomes.",
        "",
        "| Priority | Question | Type | Paths | Proxy A/B/C | Literal `None` annotations |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for index, row in enumerate(recommendations, start=1):
        lines.append(
            f"| {index} | {row['question_id']} | {row['question_type']} | "
            f"{row['path_count']} | {row['proxy_tier_a']}/{row['proxy_tier_b']}/"
            f"{row['proxy_tier_c']} | {row['literal_none_annotations']} |"
        )
    if not recommendations:
        lines.append("| — | No zero-proxy-A mechanism candidate found | — | — | — | — |")
    if excluded_holdouts:
        lines.extend(
            [
                "",
                "## Frozen holdouts excluded from development selection",
                "",
            ]
        )
        for row in excluded_holdouts:
            lines.append(
                f"- {row['question_id']} ({row['run']}): proxy "
                f"{row['proxy_tier_a']}/{row['proxy_tier_b']}/{row['proxy_tier_c']}"
            )
    lines.extend(
        [
            "",
            f"Screened legacy graph results: {len(rows)}",
            f"Recommended paid rescue tests: {len(recommendations)}",
            "",
        ]
    )
    OUTPUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
