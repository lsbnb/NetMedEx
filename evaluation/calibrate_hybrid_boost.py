#!/usr/bin/env python3
"""Calibrate AbstractRAG.search()'s preferred_pmids boost multiplier (hard-coded 1.5x) against
real relevance judgments, instead of leaving it a hand-picked constant.

For each formal question: rebuild the graph from the already-fetched corpus.pubtator (same
PubTatorGraphBuilder(edge_method="semantic", ...) params as run_formal_50.py -- this calls the
same LLM, not free), resolve the F_adaptive hybrid exposure profile via
evaluation.run_formal_50.select_hybrid_exposure (question_type-based deterministic routing, no
extra LLM call), then call AbstractRAG.search_with_components() to get the raw
(similarity, weight, is_preferred) triple per candidate PMID -- NOT the already-blended
hybrid_score, so the boost multiplier can be swept over many candidate values without re-querying
ChromaDB or rebuilding the graph for each one.

Joins against evaluation/formal_v2/qrels.csv (not evaluation/formal/qrels.csv -- the pooled
formal_v2 candidates overlap the per-question indexed corpus far better; see the module docstring
in evaluation/formal/README.md's data-collection notes for why). Grid-searches the boost
multiplier for the value that maximizes mean nDCG@10 across questions, and reports a paired
bootstrap CI comparing the current 1.5x against the empirical optimum (reusing
evaluation.metrics's _dcg/_bootstrap_mean_ci/_sign_test_p_value for consistency with the rest of
this evaluation workspace's statistical rigor).
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

from metrics import _bootstrap_mean_ci, _dcg, _sign_test_p_value
from run_formal_50 import build_documents, select_hybrid_exposure
from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.pubtator_parser import PubTatorIO
from netmedex.rag import AbstractRAG
from webapp.llm import LLMClient

DEFAULT_QUESTION_IDS = [
    "Q001", "Q004", "Q008", "Q011", "Q015", "Q016", "Q018", "Q022", "Q023", "Q025",
    "Q028", "Q029", "Q031", "Q034", "Q035", "Q037", "Q040", "Q048", "Q050",
]


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


def collect_components_for_question(
    qid: str,
    question_row: dict[str, str],
    corpus_path: Path,
    llm: LLMClient,
    semantic_threshold: float,
) -> list[dict[str, Any]]:
    collection = PubTatorIO.parse(corpus_path)

    graph_builder = PubTatorGraphBuilder(
        node_type="all", edge_method="semantic", llm_client=llm, semantic_threshold=semantic_threshold
    )
    graph_builder.add_collection(collection)
    graph = graph_builder.build(
        pmid_weights=None, weighting_method="freq", edge_weight_cutoff=1, community=False, max_edges=0
    )

    documents = build_documents(collection, graph)
    rag = AbstractRAG(llm, collection_name=f"calib_{qid.lower()}")
    rag.index_abstracts(documents)

    retriever = GraphRetriever(graph, node_rag=None)
    nodes = retriever.find_relevant_nodes(question_row["question"])
    _context, _paths, preferred_pmids, exposure = select_hybrid_exposure(
        "F_adaptive", retriever, graph, question_row["question"],
        question_type=question_row.get("question_type", ""),
    )

    components = rag.search_with_components(
        question_row["question"], top_k=len(documents), preferred_pmids=preferred_pmids
    )
    for c in components:
        c["question_id"] = qid
        c["routed_profile"] = exposure.get("routed_profile", exposure.get("profile"))
    return components


def score_boost(
    components_by_question: dict[str, list[dict[str, Any]]],
    relevance_by_question: dict[str, dict[str, float]],
    boost: float,
) -> list[float]:
    """Per-question nDCG@10 at a given boost value. Returns one value per question that has both
    component data and at least one qrels-judged candidate (independent resampling units for the
    bootstrap CI later)."""
    ndcgs = []
    for qid, components in components_by_question.items():
        gold = relevance_by_question.get(qid, {})
        judged = [c for c in components if c["pmid"] in gold]
        if not judged:
            continue
        scored = [
            (c["pmid"], c["similarity"] * c["weight"] * (boost if c["is_preferred"] else 1.0))
            for c in judged
        ]
        scored.sort(key=lambda x: (-x[1], x[0]))
        top10 = scored[:10]
        observed = [gold[pmid] for pmid, _ in top10]
        ideal = sorted(gold.values(), reverse=True)[:10]
        ideal_dcg = _dcg(ideal)
        ndcgs.append(_dcg(observed) / ideal_dcg if ideal_dcg else 0.0)
    return ndcgs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("evaluation/formal/questions.csv"))
    parser.add_argument(
        "--qrels", type=Path, default=Path("evaluation/formal_v2/qrels.csv"),
        help="formal_v2's pooled qrels overlap the per-question indexed corpus far better than "
        "formal/qrels.csv -- see this script's module docstring.",
    )
    parser.add_argument(
        "--runs-dir", type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/questions"),
    )
    parser.add_argument("--question-ids", nargs="+", default=DEFAULT_QUESTION_IDS)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--semantic-threshold", type=float, default=0.5)
    parser.add_argument(
        "--boost-grid", nargs="+", type=float,
        default=[1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.5, 3.0],
    )
    parser.add_argument("--output", type=Path, default=Path("evaluation/formal/hybrid_boost_components.csv"))
    args = parser.parse_args()

    load_dotenv(override=True)
    llm = init_llm(args.model)

    questions = {row["question_id"]: row for row in read_csv(args.questions)}
    qrels_rows = read_csv(args.qrels)
    relevance_by_question: dict[str, dict[str, float]] = defaultdict(dict)
    for row in qrels_rows:
        relevance_by_question[row["question_id"]][row["pmid"]] = float(row["relevance"])

    components_by_question: dict[str, list[dict[str, Any]]] = {}
    all_rows: list[dict[str, Any]] = []
    for idx, qid in enumerate(args.question_ids, 1):
        corpus_path = args.runs_dir / qid / "corpus.pubtator"
        if not corpus_path.exists():
            print(f"[{idx}/{len(args.question_ids)}] {qid}: no corpus.pubtator, skipping")
            continue
        print(f"[{idx}/{len(args.question_ids)}] Scoring {qid}...", flush=True)
        components = collect_components_for_question(
            qid, questions[qid], corpus_path, llm, args.semantic_threshold
        )
        components_by_question[qid] = components
        judged = sum(1 for c in components if c["pmid"] in relevance_by_question.get(qid, {}))
        print(f"  -> {len(components)} candidates, {judged} with a qrels label", flush=True)
        all_rows.extend(components)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["question_id", "pmid", "similarity", "weight", "is_preferred", "routed_profile"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nRaw components written to {args.output}")

    print("\n=== Boost grid search (mean nDCG@10 across questions with >=1 qrels-judged candidate) ===")
    results = {}
    for boost in args.boost_grid:
        ndcgs = score_boost(components_by_question, relevance_by_question, boost)
        results[boost] = ndcgs
        print(f"  boost={boost:.2f}: n_questions={len(ndcgs)}, mean_ndcg@10={mean(ndcgs):.4f}" if ndcgs else f"  boost={boost:.2f}: no judged questions")

    if not results or not any(results.values()):
        print("No questions had both component data and qrels labels -- cannot calibrate.")
        return

    best_boost = max(results, key=lambda b: mean(results[b]) if results[b] else -1)
    current_ndcgs = results.get(1.5, [])
    best_ndcgs = results[best_boost]

    print(f"\nCurrent boost (1.5x): mean nDCG@10 = {mean(current_ndcgs):.4f}" if current_ndcgs else "\nCurrent boost (1.5x) not in grid")
    print(f"Best grid boost ({best_boost}x): mean nDCG@10 = {mean(best_ndcgs):.4f}")

    if current_ndcgs and best_boost != 1.5:
        # Paired per-question diff (best boost's nDCG@10 minus current 1.5x's), same question set
        shared_qids = [
            qid for qid in components_by_question
            if qid in relevance_by_question and any(c["pmid"] in relevance_by_question[qid] for c in components_by_question[qid])
        ]
        diffs = []
        for qid in shared_qids:
            gold = relevance_by_question[qid]
            comps = components_by_question[qid]
            judged = [c for c in comps if c["pmid"] in gold]
            if not judged:
                continue

            def ndcg_at(boost_value):
                scored = sorted(
                    [(c["pmid"], c["similarity"] * c["weight"] * (boost_value if c["is_preferred"] else 1.0)) for c in judged],
                    key=lambda x: (-x[1], x[0]),
                )[:10]
                observed = [gold[p] for p, _ in scored]
                ideal = sorted(gold.values(), reverse=True)[:10]
                ideal_dcg = _dcg(ideal)
                return _dcg(observed) / ideal_dcg if ideal_dcg else 0.0

            diffs.append(ndcg_at(best_boost) - ndcg_at(1.5))

        if diffs:
            point, lo, hi = _bootstrap_mean_ci(diffs)
            p = _sign_test_p_value(diffs)
            print(f"\nPaired per-question delta (best={best_boost}x minus current=1.5x nDCG@10):")
            print(f"  n_questions={len(diffs)}, mean_diff={point}, 95% bootstrap CI=[{lo}, {hi}], sign_test_p={p}")


if __name__ == "__main__":
    main()
