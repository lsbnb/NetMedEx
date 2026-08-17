#!/usr/bin/env python3
"""Reapply the deterministic path gate to frozen candidates without LLM calls."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import networkx as nx

from netmedex.graph_rag import GraphRetriever
from netmedex.pubtator_parser import PubTatorIO


def corpus_aliases(corpus_path: Path) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    collection = PubTatorIO.parse(corpus_path)
    for article in collection.articles:
        for annotation in article.annotations:
            if annotation.mesh not in {"", "-"}:
                node_ids = annotation.get_mesh_node_id()
            else:
                name = annotation.get_standardized_name()
                node_ids = [annotation.get_non_mesh_node_id(name)]
            for node_id in node_ids:
                aliases.setdefault(node_id, set()).add(str(annotation.name))
    return aliases


def lexical_endpoint_ids(graph: nx.Graph, phrase: str) -> set[str]:
    phrase_tokens = {
        token
        for token in GraphRetriever._normalize_anchor_text(phrase).split()
        if len(token) >= 3
    }
    scored = []
    for node_id, data in graph.nodes(data=True):
        values = {str(data.get("name", "")), *map(str, data.get("aliases", set()) or set())}
        overlap = set()
        for value in values:
            overlap.update(
                phrase_tokens
                & set(GraphRetriever._normalize_anchor_text(value).split())
            )
        if overlap and (len(overlap) >= 2 or max(map(len, overlap)) >= 5):
            scored.append(((len(overlap), max(map(len, overlap))), str(node_id)))
    if not scored:
        return set()
    best = max(score for score, _node_id in scored)
    return {node_id for score, node_id in scored if score == best}


def regate_result(result: dict, corpus_path: Path) -> dict:
    candidates = list(result.get("graph", {}).get("pre_gate_candidates", []))
    aliases = corpus_aliases(corpus_path)
    graph = nx.Graph()
    semantic_ids: set[str] = set()
    for candidate in candidates:
        node_ids = candidate.get("node_ids", [])
        names = candidate.get("names", [])
        for node_id, name in zip(node_ids, names):
            graph.add_node(
                node_id,
                name=name,
                aliases=aliases.get(node_id, {name}),
                type="unknown",
            )
        for left, right in zip(node_ids, node_ids[1:]):
            if not graph.has_edge(left, right):
                graph.add_edge(left, right)
        features = candidate.get("anchor_features", {})
        semantic_ids.update(features.get("context_anchor_ids", []))

    retriever = GraphRetriever(graph)
    semantic_source_ids: set[str] = set()
    semantic_target_ids: set[str] = set()
    endpoint_phrases = retriever._extract_endpoint_phrases(result.get("question", ""))
    if endpoint_phrases:
        source_phrase, target_phrase = endpoint_phrases
        semantic_source_ids = lexical_endpoint_ids(graph, source_phrase)
        semantic_target_ids = lexical_endpoint_ids(graph, target_phrase)
    anchors = retriever._extract_query_anchors(
        result.get("question", ""),
        {node_id: 1.0 for node_id in semantic_ids},
        semantic_source_ids=semantic_source_ids,
        semantic_target_ids=semantic_target_ids,
    )
    for rank, candidate in enumerate(candidates, start=1):
        path = candidate.get("node_ids", [])
        candidate["node_aliases"] = [
            sorted(aliases.get(node_id, {name}))
            for node_id, name in zip(path, candidate.get("names", []))
        ]
        bonus, features = retriever._score_path_anchors(path, anchors)
        old_features = candidate.get("anchor_features", {})
        if len(path) == 3 and old_features.get("bridge_matches_mechanism_context"):
            features["bridge_matches_mechanism_context"] = True
            features["path_spans_multiple_anchor_types"] = bool(
                features["start_matches_query_focus"]
                or features["end_matches_query_focus"]
            )
            bonus = min(
                0.12,
                (0.04 if features["end_matches_query_focus"] else 0.0)
                + 0.04
                + (0.04 if features["path_spans_multiple_anchor_types"] else 0.0),
            )
        old_bonus = float(candidate.get("anchor_bonus", 0.0) or 0.0)
        candidate["score"] = float(candidate.get("score", 0.0) or 0.0) - old_bonus + bonus
        candidate["anchor_bonus"] = bonus
        candidate["anchor_features"] = features
        refreshed_supports = []
        old_supports = candidate.get("edge_supports", [])
        for index, relation in enumerate(candidate.get("relations", [])):
            pmids = candidate.get("edge_pmids", [[]])[index] or []
            quotes = candidate.get("edge_evidence_quotes", [[]])[index] or []
            old_support = old_supports[index] if index < len(old_supports) else {}
            confidence = old_support.get("selected_confidence")
            edge_data = {
                "relations": {str(pmid): {relation} for pmid in pmids},
                "evidences": {
                    str(pmid): {
                        relation: quotes[min(pmid_index, len(quotes) - 1)]
                        if quotes
                        else ""
                    }
                    for pmid_index, pmid in enumerate(pmids)
                },
                "confidences": {
                    str(pmid): {relation: confidence}
                    for pmid in pmids
                    if confidence is not None
                },
            }
            refreshed_supports.append(retriever._select_edge_support(edge_data))
        candidate["edge_supports"] = refreshed_supports
        candidate["edge_evidence_complete"] = [
            support.get("support_tier") == "A" for support in refreshed_supports
        ]
        gate = retriever._classify_path_gate(path, refreshed_supports, features)
        if any(
            str(reason).startswith("direction_contradicted")
            for reason in candidate.get("gate_reasons", [])
        ):
            gate = {
                "gate_tier": "C",
                "gate_reasons": list(candidate.get("gate_reasons", [])),
                "claim_safe": False,
                "retrieval_safe": False,
            }
        candidate.update(gate)
        candidate["candidate_rank"] = rank

    selected, _, _ = retriever._select_gated_candidate_paths(candidates)
    result["graph"]["pre_gate_candidates"] = candidates
    result["graph"]["paths"] = selected
    result["graph"]["path_count"] = len(selected)
    result["graph"]["offline_regated"] = True
    result["graph"]["offline_regate_alias_aware"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-run", type=Path, required=True)
    parser.add_argument("--output-run", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    args.output_run.mkdir(parents=True, exist_ok=True)
    for result_path in sorted((args.input_run / "questions").glob("*/result.json")):
        question_id = result_path.parent.name
        if args.only and question_id not in set(args.only):
            continue
        output_dir = args.output_run / "questions" / question_id
        output_dir.mkdir(parents=True, exist_ok=True)
        corpus_path = result_path.with_name("corpus.pubtator")
        result = regate_result(
            json.loads(result_path.read_text(encoding="utf-8")), corpus_path
        )
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        shutil.copy2(corpus_path, output_dir / "corpus.pubtator")
        manifest = result_path.with_name("corpus_manifest.json")
        if manifest.exists():
            shutil.copy2(manifest, output_dir / "corpus_manifest.json")
        print(f"regated {question_id}: {len(result['graph']['paths'])} selected paths")


if __name__ == "__main__":
    main()
