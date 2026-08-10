#!/usr/bin/env python3
"""Rebuild and audit the fixed-endpoint Icariin acceptance graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder, load_graph, save_graph
from netmedex.graph_rag import GraphRetriever
from netmedex.graph_schema import graph_schema_status
from netmedex.pubtator_parser import PubTatorIO
from webapp.llm import LLMClient
from webapp.llm import OPENAI_BASE_URL


def _matching_nodes(graph, terms: tuple[str, ...]) -> list[str]:
    matches = []
    for node_id, data in graph.nodes(data=True):
        values = {
            str(data.get("name", "")).casefold(),
            *(str(alias).casefold() for alias in data.get("aliases", set()) or set()),
        }
        if any(term in value for term in terms for value in values):
            matches.append(node_id)
    return sorted(matches)


def _hop_audit(graph, path: list[str]) -> list[dict]:
    hops = []
    for source, target in zip(path, path[1:]):
        support = GraphRetriever._select_edge_support(graph.edges[source, target])
        hops.append(
            {
                "source_id": source,
                "source_name": graph.nodes[source].get("name", source),
                "target_id": target,
                "target_name": graph.nodes[target].get("name", target),
                "relation": support["selected_relation"],
                "pmid": support["selected_pmid"],
                "evidence": support["selected_quote"],
                "confidence": support["selected_confidence"],
                "support_tier": support["support_tier"],
            }
        )
    return hops


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--reuse-graph", action="store_true")
    args = parser.parse_args()

    collection = PubTatorIO.parse(args.corpus)
    if args.reuse_graph:
        graph = load_graph(args.graph)
    else:
        llm = LLMClient()
        llm.initialize_client(
            provider="openai", base_url=OPENAI_BASE_URL, model=args.model
        )
        if llm.client is None:
            raise RuntimeError("OPENAI_API_KEY is unavailable")

        builder = PubTatorGraphBuilder(
            node_type="all", edge_method="semantic", llm_client=llm,
            semantic_threshold=0.5,
        )
        builder.add_collection(collection)
        graph = builder.build(
            pmid_weights=None, weighting_method="freq", edge_weight_cutoff=1,
            community=False, max_edges=0,
        )
    semantic_stats = graph.graph.get("semantic_stats", {})
    if (
        semantic_stats.get("failed_articles")
        or semantic_stats.get("succeeded_articles") != len(collection.articles)
        or graph.number_of_edges() == 0
    ):
        raise RuntimeError(f"semantic graph rebuild failed closed: {semantic_stats}")
    if not args.reuse_graph:
        save_graph(graph, args.graph, "pickle")

    source_ids = _matching_nodes(graph, ("icariin",))
    target_ids = _matching_nodes(
        graph, ("osteoblast differentiation", "osteogenesis")
    )
    accepted = []
    exposed = []
    shorter_claim_safe = []
    for target_id in target_ids:
        target_name = graph.nodes[target_id].get("name", target_id)
        query = (
            "Which evidence-supported intermediates connect Icariin to "
            f"{target_name}?"
        )
        for source_id in source_ids:
            retriever = GraphRetriever(graph)
            _context, paths = retriever.get_subgraph_context_with_paths(
                [source_id], query=query, max_hops=4
            )
            for path in paths:
                ids = path.get("node_ids", [])
                if not ids or ids[0] != source_id or ids[-1] != target_id:
                    continue
                record = {
                    "target": target_name,
                    "node_ids": ids,
                    "node_names": [graph.nodes[node].get("name", node) for node in ids],
                    "hop_count": path.get("hop_count"),
                    "gate_tier": path.get("gate_tier"),
                    "claim_safe": path.get("claim_safe"),
                    "gate_reasons": path.get("gate_reasons", []),
                    "hops": _hop_audit(graph, ids),
                }
                if path.get("hop_count") in {1, 2}:
                    if record["gate_tier"] == "A" and record["claim_safe"]:
                        shorter_claim_safe.append(record)
                    continue
                if path.get("hop_count") not in {3, 4}:
                    continue
                exposed.append(record)
                if (
                    record["gate_tier"] == "A"
                    and record["claim_safe"]
                    and all(hop["pmid"] and hop["evidence"] for hop in record["hops"])
                ):
                    accepted.append(record)

    # Exhaustively audit the bounded fixed-endpoint space as well as the paths
    # surfaced by ranking.  This distinguishes "retriever missed it" from
    # "every available path fails evidence/direction gating".
    bounded_candidates = []
    retriever = GraphRetriever(graph)
    for source_id in source_ids:
        for target_id in target_ids:
            target_name = graph.nodes[target_id].get("name", target_id)
            fixed_query = (
                "Which evidence-supported intermediates connect Icariin to "
                f"{target_name}?"
            )
            anchors = retriever._extract_query_anchors(fixed_query, {})
            for node_ids in nx.all_simple_paths(graph, source_id, target_id, cutoff=4):
                hop_count = len(node_ids) - 1
                if hop_count not in {3, 4}:
                    continue
                anchor_bonus, anchor_features = retriever._score_path_anchors(
                    node_ids, anchors
                )
                structured = retriever._build_structured_path_entry(
                    {
                        "path": node_ids,
                        "score": anchor_bonus,
                        "base_score": 0.0,
                        "anchor_bonus": anchor_bonus,
                        "anchor_features": anchor_features,
                    },
                    len(bounded_candidates) + 1,
                )
                bounded_candidates.append(
                    {
                        "node_ids": node_ids,
                        "node_names": [
                            graph.nodes[node].get("name", node) for node in node_ids
                        ],
                        "hop_count": hop_count,
                        "gate_tier": structured.get("gate_tier"),
                        "claim_safe": structured.get("claim_safe"),
                        "gate_reasons": structured.get("gate_reasons", []),
                        "hops": _hop_audit(graph, node_ids),
                    }
                )

    gene_context = []
    for node_id in _matching_nodes(graph, ("mir21", "mir-21", "mirna-21", "pten")):
        data = graph.nodes[node_id]
        if str(data.get("type", "")).casefold() != "gene":
            continue
        gene_context.append(
            {
                "node_id": node_id,
                "name": data.get("name"),
                "pmids": sorted(data.get("pmids", [])),
                "study_species_by_pmid": data.get("study_species_by_pmid", {}),
            }
        )

    report = {
        "criterion": {
            "source": "Icariin",
            "targets": ["osteoblast differentiation", "osteogenesis"],
            "allowed_hops": [3, 4],
            "requirements": [
                "Tier-A claim-safe path",
                "PMID and evidence quote on every hop",
                "distinct Gene identifiers are never merged across species",
            ],
        },
        "graph": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "schema": graph_schema_status(graph),
            "semantic_stats": semantic_stats,
        },
        "gene_identity_context": gene_context,
        "accepted_endpoint_paths": accepted,
        "all_exposed_endpoint_paths": exposed,
        "shorter_claim_safe_endpoint_paths": shorter_claim_safe,
        "all_bounded_endpoint_candidates": bounded_candidates,
        "verdict": "pass" if accepted else "no_strict_3_or_4_hop_path",
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "graph": report["graph"],
        "gene_nodes": len(gene_context),
        "exposed_paths": len(exposed),
        "accepted_paths": len(accepted),
        "verdict": report["verdict"],
    }, indent=2))


if __name__ == "__main__":
    main()
