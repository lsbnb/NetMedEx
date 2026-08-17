#!/usr/bin/env python3
"""Audit whether bridge-withheld questions can test graph-incremental retrieval."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.pubtator_parser import PubTatorIO


def load_questions(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["question_id"]: row["question"] for row in csv.DictReader(handle)}


def compatible_node_ids(graph, phrase: str) -> list[str]:
    return sorted(
        str(node_id)
        for node_id, node_data in graph.nodes(data=True)
        if GraphRetriever._endpoint_lexically_compatible(
            phrase, str(node_id), node_data
        )
    )


def audit_question(
    question_id: str,
    question: str,
    corpus_path: Path,
    text_top_k: int,
    min_documents: int,
) -> dict:
    collection = PubTatorIO.parse(str(corpus_path))
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    builder.add_collection(collection)
    graph = builder.build(edge_weight_cutoff=0, community=False)
    endpoint_phrases = GraphRetriever._extract_endpoint_phrases(question)
    source_ids: list[str] = []
    target_ids: list[str] = []
    if endpoint_phrases:
        source_ids = compatible_node_ids(graph, endpoint_phrases[0])
        target_ids = compatible_node_ids(graph, endpoint_phrases[1])

    document_count = len(collection.articles)
    reasons = []
    if not endpoint_phrases:
        reasons.append("endpoint_phrases_unparsed")
    if endpoint_phrases and not source_ids:
        reasons.append("source_endpoint_not_represented")
    if endpoint_phrases and not target_ids:
        reasons.append("target_endpoint_not_represented")
    if document_count <= text_top_k:
        reasons.append("no_documents_outside_text_top_k")
    if document_count < min_documents:
        reasons.append("corpus_below_minimum_size")

    return {
        "question_id": question_id,
        "question": question,
        "corpus_path": str(corpus_path),
        "document_count": document_count,
        "text_top_k": text_top_k,
        "min_documents": min_documents,
        "endpoint_phrases": list(endpoint_phrases) if endpoint_phrases else None,
        "source_node_ids": source_ids,
        "target_node_ids": target_ids,
        "eligible_for_incremental_screen": not reasons,
        "ineligibility_reasons": reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch-dir", type=Path, default=Path("evaluation/formal/bridge_withheld_dev_v1")
    )
    parser.add_argument("--text-top-k", type=int, default=10)
    parser.add_argument("--min-documents", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    questions = load_questions(args.batch_dir / "queries.csv")
    rows = [
        audit_question(
            question_id,
            question,
            args.batch_dir / "questions" / question_id / "corpus.pubtator",
            args.text_top_k,
            args.min_documents,
        )
        for question_id, question in questions.items()
    ]
    report = {
        "method": "bridge_withheld_eligibility_v1",
        "batch_dir": str(args.batch_dir),
        "text_top_k": args.text_top_k,
        "min_documents": args.min_documents,
        "question_count": len(rows),
        "eligible_count": sum(row["eligible_for_incremental_screen"] for row in rows),
        "questions": rows,
    }
    output = args.output or args.batch_dir / "eligibility_audit.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output}; eligible={report['eligible_count']}/{len(rows)}")


if __name__ == "__main__":
    main()
