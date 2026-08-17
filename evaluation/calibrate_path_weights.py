#!/usr/bin/env python3
"""Phase 1+2 of Task B: rebuild the 14 edge_ratings.csv questions' graphs, capture the raw
per-edge scoring components (npmi, calibrated_conf, rel_score) that graph_rag.py's
calculate_score() blends into a single final_score, and join them against the existing
biologically_meaningful/relation_type_correct AI ratings.

Then run a QUICK, uncalibrated grid search over the weight simplex (w_npmi + w_conf + w_rel = 1)
to see how far the hand-tuned 0.3/0.4/0.3 split sits from the empirical optimum on this dataset.
This is deliberately NOT the full Task B (no leave-one-question-out CV, no bootstrap CI, no sign
test, no documentation) -- per the phased plan, phases 3-4 (rigorous fit + write-up) are only
worth doing if this quick look shows a gap larger than what looks like noise.

edge_method="semantic" re-runs the same LLM (gpt-5.6-terra) used for the original edge_ratings
extraction -- this is not free. There is no on-disk cache for semantic edges (SemanticRelationship
Extractor.cache is in-memory only), so every run re-incurs the API cost.

Rebuilt edges are matched back to rated (source, target, relation_type) rows by unordered
name pair -- the graph is undirected, and "source"/"target" order in edge_ratings.csv reflects
the traversal direction at rating time, not an inherent edge direction. Rows whose edge doesn't
reappear in this rerun (semantic extraction is not perfectly reproducible -- see
evaluation/formal/README.md's note on score_edge_verification_delta) are reported as unmatched
and dropped, not silently ignored.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from dotenv import load_dotenv

from build_edge_ratings_worksheet import build_node_rag
from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.pubtator_parser import PubTatorIO
from webapp.llm import LLMClient

DEFAULT_RATINGS = Path("evaluation/formal/edge_ratings.csv")
DEFAULT_QUESTIONS = Path("evaluation/formal/questions.csv")
DEFAULT_RUNS_DIR = Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/questions")
DEFAULT_OUTPUT = Path("evaluation/formal/path_score_components.csv")


def init_llm(model: str) -> LLMClient:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = LLMClient()
    client.initialize_client(
        provider="openai", api_key=api_key, base_url="https://api.openai.com/v1", model=model
    )
    return client


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_rated_edges(ratings_path: Path) -> dict[str, dict[tuple[str, str], dict[str, Any]]]:
    """question_id -> {(source, target, relation_type): {"bio": [..], "reltype": [..]}}."""
    by_question: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for row in read_csv(ratings_path):
        qid = row["question_id"] if "question_id" in row else row["edge_id"].rsplit("-E", 1)[0]
        key = (
            row["source"].strip().lower(),
            row["target"].strip().lower(),
            row["relation_type"].strip().lower(),
        )
        entry = by_question[qid].setdefault(key, {"bio": [], "reltype": []})
        entry["bio"].append(float(row["biologically_meaningful"]))
        entry["reltype"].append(float(row["relation_type_correct"]))
    return by_question


def collect_components_for_question(
    qid: str,
    question_text: str,
    corpus_path: Path,
    llm: LLMClient,
    semantic_threshold: float,
    rated_edges: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    collection = PubTatorIO.parse(corpus_path)

    graph_builder = PubTatorGraphBuilder(
        node_type="all", edge_method="semantic", llm_client=llm, semantic_threshold=semantic_threshold
    )
    graph_builder.add_collection(collection)
    graph = graph_builder.build(
        pmid_weights=None, weighting_method="freq", edge_weight_cutoff=1, community=False, max_edges=0
    )

    node_rag = build_node_rag(llm, graph, collection_name=f"calib_pw_{qid.lower()}")
    retriever = GraphRetriever(graph, node_rag=node_rag)

    max_edge_weight = 1e-6
    for _, _, data in graph.edges(data=True):
        w = data.get("edge_weight", 0)
        if w > max_edge_weight:
            max_edge_weight = w

    semantic_relevance_map: dict[str, float] = {}
    if node_rag:
        hits = node_rag.search_nodes(question_text, top_k=100)
        semantic_relevance_map = {node_id: score for node_id, score, _ in hits}

    # (name_u, name_v) unordered pair -> (u, v, edge_data); the graph is undirected so a rated
    # edge's recorded source/target order need not match how the pair is stored here.
    pair_to_edge: dict[frozenset, tuple[str, str, dict]] = {}
    for u, v, data in graph.edges(data=True):
        u_name = str(graph.nodes[u].get("name", u)).strip().lower()
        v_name = str(graph.nodes[v].get("name", v)).strip().lower()
        pair_to_edge[frozenset((u_name, v_name))] = (u, v, data)

    rows = []
    matched = 0
    for (source, target, relation_type), labels in rated_edges.items():
        edge = pair_to_edge.get(frozenset((source, target)))
        if edge is None:
            continue
        u, v, edge_data = edge
        rel_types = set()
        for pmid_rels in (edge_data.get("relations", {}) or {}).values():
            rel_types.update(t.lower() for t in pmid_rels)
        if relation_type not in rel_types:
            continue
        matched += 1
        components = retriever.score_edge_components(
            u, v, edge_data, max_edge_weight, semantic_relevance_map
        )
        rows.append(
            {
                "question_id": qid,
                "source": source,
                "target": target,
                "relation_type": relation_type,
                **components,
                "biologically_meaningful_mean": mean(labels["bio"]),
                "relation_type_correct_mean": mean(labels["reltype"]),
                "n_raters": len(labels["bio"]),
            }
        )
    return rows, len(rated_edges) - matched


def quick_weight_scan(rows: list[dict[str, Any]], label_field: str, step: float = 0.05):
    """Grid-search (w_npmi, w_conf) with w_rel = 1 - w_npmi - w_conf over the simplex, scoring
    each split by Pearson correlation between base_score and the binary/averaged label. This is
    the "quick look" -- no cross-validation, no CI. A large, one-directional gap here is the
    trigger for investing in the full Task B fit (phases 3-4); a small/noisy gap is the signal
    to stop here, matching Task A's outcome.
    """
    npmi = np.array([r["npmi"] for r in rows])
    conf = np.array([r["calibrated_conf"] for r in rows])
    rel = np.array([r["rel_score"] for r in rows])
    label = np.array([r[label_field] for r in rows])

    if np.std(label) == 0:
        return None

    def corr(w_npmi, w_conf, w_rel):
        score = npmi * w_npmi + conf * w_conf + rel * w_rel
        if np.std(score) == 0:
            return -2.0
        return float(np.corrcoef(score, label)[0, 1])

    current = corr(0.3, 0.4, 0.3)

    best = (-2.0, None)
    grid = np.arange(0.0, 1.0 + 1e-9, step)
    for w_npmi in grid:
        for w_conf in grid:
            w_rel = 1.0 - w_npmi - w_conf
            if w_rel < -1e-9:
                continue
            w_rel = max(0.0, w_rel)
            c = corr(w_npmi, w_conf, w_rel)
            if c > best[0]:
                best = (c, (round(w_npmi, 2), round(w_conf, 2), round(w_rel, 2)))

    return {"current_weights_corr": current, "best_weights": best[1], "best_corr": best[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--semantic-threshold", type=float, default=0.5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--question-ids", nargs="+", default=None,
        help="Restrict to these question IDs (default: all questions present in --ratings). "
        "Useful for a cheap single-question dry run before the full paid rebuild.",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    llm = init_llm(args.model)

    questions = {row["question_id"]: row for row in read_csv(args.questions)}
    rated_by_question = load_rated_edges(args.ratings)

    all_rows: list[dict[str, Any]] = []
    total_unmatched = 0
    qids = sorted(args.question_ids) if args.question_ids else sorted(rated_by_question)
    for idx, qid in enumerate(qids, 1):
        corpus_path = args.runs_dir / qid / "corpus.pubtator"
        if not corpus_path.exists():
            print(f"[{idx}/{len(qids)}] {qid}: no corpus.pubtator, skipping")
            continue
        print(f"[{idx}/{len(qids)}] Scoring {qid} ({len(rated_by_question[qid])} rated edges)...", flush=True)
        rows, unmatched = collect_components_for_question(
            qid,
            questions[qid]["question"],
            corpus_path,
            llm,
            args.semantic_threshold,
            rated_by_question[qid],
        )
        print(f"  -> matched {len(rows)}/{len(rated_by_question[qid])}, unmatched {unmatched}", flush=True)
        all_rows.extend(rows)
        total_unmatched += unmatched

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if all_rows:
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
    print(f"\n{len(all_rows)} matched rows written to {args.output} ({total_unmatched} rated edges unmatched)")

    if not all_rows:
        print("No matched rows -- cannot run the quick weight scan.")
        return

    for label_field in ("biologically_meaningful_mean", "relation_type_correct_mean"):
        print(f"\n=== Quick weight scan vs. {label_field} (n={len(all_rows)}, NO cross-validation) ===")
        result = quick_weight_scan(all_rows, label_field)
        if result is None:
            print("  label has zero variance, skipping")
            continue
        print(f"  current (0.30/0.40/0.30) correlation: {result['current_weights_corr']:.4f}")
        print(f"  best grid weights {result['best_weights']} (npmi/conf/rel): correlation {result['best_corr']:.4f}")
        print(f"  gap: {result['best_corr'] - result['current_weights_corr']:.4f}")


if __name__ == "__main__":
    main()
