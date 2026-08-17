#!/usr/bin/env python3
"""Run the frozen 50-question NetMedEx evaluation without reading gold qrels."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import logging
import os
import pickle
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
from dotenv import load_dotenv

from netmedex.claim_verifier import verify_answer_graph_claims
from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.hybrid_retrieval import (
    PersistentGraphCache,
    build_pubmed_expansion_queries,
    filter_expansion_paths,
    merge_expanded_ranking,
    route_query,
)
from netmedex.node_rag import GraphNode, NodeRAG
from netmedex.pubtator import PubTatorAPI
from netmedex.pubtator_parser import PubTatorIO
from netmedex.rag import AbstractDocument, AbstractRAG
from webapp.llm import LLMClient


LOGGER = logging.getLogger("formal-evaluation")
SYSTEMS = ("netmedex_hybrid_rag", "traditional_rag", "general_llm")
HYBRID_PROFILES = {
    "legacy": {
        "label": "Legacy Hybrid",
        "use_node_rag": False,
        "max_hops": 2,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": True,
    },
    "A_text_only": {
        "label": "A. Text-only RAG",
        "use_node_rag": False,
        "max_hops": 0,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": False,
    },
    "B_entity_validated": {
        "label": "B. Text + normalized entities",
        "use_node_rag": True,
        "max_hops": 0,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": False,
    },
    "C_one_hop": {
        "label": "C. 1-hop Graph RAG",
        "use_node_rag": True,
        "max_hops": 1,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": True,
    },
    "D_two_hop": {
        "label": "D. 2-hop Graph RAG",
        "use_node_rag": True,
        "max_hops": 2,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": True,
    },
    "E_verified_gated_two_hop": {
        "label": "E. Verified + gated 2-hop",
        "use_node_rag": True,
        "max_hops": 2,
        "gate_directional_paths": True,
        "gate_multi_document_paths": True,
        "use_graph_context": True,
        "gate_evidence_paths": True,
    },
    "G_evidence_gated_two_hop": {
        "label": "G. Evidence-gated 2-hop Graph RAG",
        "use_node_rag": True,
        "max_hops": 2,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "gate_evidence_paths": True,
        "use_graph_context": True,
    },
    "H_evidence_gated_four_hop": {
        "label": "H. Evidence-gated bounded 4-hop Graph RAG",
        "use_node_rag": True,
        "max_hops": 4,
        "gate_directional_paths": False,
        # Cross-PMID paths are preferred below, not required. A fully evidenced
        # Tier-A path from one PMID remains valid support, but must not be
        # reported as cross-document discovery.
        "gate_multi_document_paths": False,
        "gate_evidence_paths": True,
        "use_graph_context": True,
    },
    "F_adaptive": {
        "label": "F. Adaptive routed Hybrid RAG",
        "use_node_rag": True,
        "max_hops": 2,
        "gate_directional_paths": False,
        "gate_multi_document_paths": False,
        "use_graph_context": True,
        "adaptive_routing": True,
    },
}

ADAPTIVE_TWO_HOP_TYPES = {
    "mechanism",
    "hypothesis",
    "two_hop_path",
    "multilingual_mechanism",
}
ADAPTIVE_ONE_HOP_TYPES = {
    "association",
    "cross_species",
    "multilingual_association",
}
ADAPTIVE_TEXT_ONLY_TYPES = {"retrieval", "direct_evidence"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def require_nonempty_semantic_graph(
    graph: nx.Graph, corpus_document_count: int
) -> None:
    """Fail closed when a live semantic extraction silently yields no graph."""
    if corpus_document_count > 0 and graph.number_of_nodes() == 0:
        raise RuntimeError(
            "Semantic graph extraction produced zero nodes from a non-empty "
            f"corpus ({corpus_document_count} articles); probable provider "
            "or extraction failure"
        )


def load_queries(path: Path, expected_count: int = 50) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"question_id", "domain", "question", "pubmed_query", "language"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Invalid query file: {path}")
    if len(rows) != expected_count or len({row["question_id"] for row in rows}) != expected_count:
        raise ValueError(
            f"Run requires exactly {expected_count} unique questions, found {len(rows)}"
        )
    return rows


def enrich_query_metadata(
    rows: list[dict[str, str]], questions_path: Path | None
) -> list[dict[str, str]]:
    """Attach frozen benchmark metadata without exposing qrels or gold PMIDs to the runner."""
    if questions_path is None:
        return rows
    with questions_path.open(newline="", encoding="utf-8") as handle:
        metadata = {row["question_id"]: row for row in csv.DictReader(handle)}
    missing = [row["question_id"] for row in rows if row["question_id"] not in metadata]
    if missing:
        raise ValueError(f"Question metadata missing IDs: {missing}")
    for row in rows:
        item = metadata[row["question_id"]]
        row["question_type"] = item.get("question_type", "").strip().lower()
    return rows


def adaptive_route_for_question(question_type: str, question: str) -> tuple[str, str]:
    """Choose a transparent graph exposure profile for the frozen evaluation.

    The router is deliberately deterministic and type-based: it can be audited without another
    LLM call, and its decisions cannot drift between repeated runs. Keyword fallback is used only
    when a benchmark question has no curated question_type metadata.
    """
    decision = route_query(question_type, question)
    if decision.use_graph:
        return "H_evidence_gated_four_hop", decision.reason
    return "A_text_only", decision.reason


def resolve_hybrid_profile(
    profile: str, question_type: str, question: str
) -> tuple[str, str]:
    if profile == "F_adaptive":
        return adaptive_route_for_question(question_type, question)
    return profile, "fixed profile"


def pubmed_esearch(query: str, retmax: int, retries: int = 4) -> list[str]:
    params = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "retmode": "json",
            "retmax": retmax,
            "sort": "relevance",
            "term": query,
            "tool": "netmedex_formal_eval",
        }
    )
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "NetMedEx-formal-eval/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))["esearchresult"]
            return [str(pmid) for pmid in result.get("idlist", [])]
        except Exception as exc:
            last_error = exc
            LOGGER.warning("ESearch attempt %s/%s failed: %s", attempt, retries, exc)
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"PubMed ESearch failed: {last_error}")


def pubmed_esearch_with_relaxation(
    query: str, retmax: int
) -> tuple[list[str], str, list[str]]:
    """Drop trailing terms only when the frozen query returns no records."""
    terms = query.split()
    attempts = [query]
    pmids = pubmed_esearch(query, retmax)
    while not pmids and len(terms) > 2:
        terms = terms[:-1]
        relaxed_query = " ".join(terms)
        attempts.append(relaxed_query)
        LOGGER.warning("No PubMed records; retrying with: %s", relaxed_query)
        pmids = pubmed_esearch(relaxed_query, retmax)
    return pmids, attempts[-1], attempts


def init_llm(model: str, provider: str = "openai") -> LLMClient:
    load_dotenv(override=True)
    client = LLMClient()
    if provider == "local":
        client.initialize_client(
            provider="local",
            api_key=os.getenv("LOCAL_LLM_API_KEY") or "local-dummy-key",
            base_url=os.getenv("LOCAL_LLM_BASE_URL") or "http://localhost:11434/v1",
            model=model,
        )
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is missing")
        client.initialize_client(provider="anthropic", api_key=api_key, model=model)
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")
        client.initialize_client(
            provider="openai",
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            model=model,
        )
    else:
        raise ValueError(f"Unsupported formal-run provider: {provider}")
    return client


def collect_pmid_edges(graph) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for source, target, data in graph.edges(data=True):
        relations = data.get("relations", {})
        relation_pmids = relations.keys() if isinstance(relations, dict) else []
        fallback_pmids = data.get("pmids", [])
        if isinstance(fallback_pmids, str):
            fallback_pmids = [fallback_pmids]
        for pmid in set(map(str, relation_pmids)) | set(map(str, fallback_pmids)):
            result.setdefault(pmid, []).append(
                {
                    "source": str(source),
                    "target": str(target),
                    "relations": sorted(relations.get(pmid, []))
                    if isinstance(relations, dict)
                    else [],
                }
            )
    return result


def build_node_rag(llm: LLMClient, graph, collection_name: str) -> NodeRAG | None:
    try:
        node_rag = NodeRAG(llm, collection_name=collection_name)
        graph_nodes = [
            GraphNode(
                node_id=str(node_id),
                name=str(data.get("name", node_id)),
                type=str(data.get("type", "Entity")),
                metadata=data,
            )
            for node_id, data in graph.nodes(data=True)
        ]
        node_rag.index_nodes(graph_nodes)
        return node_rag
    except Exception as exc:
        LOGGER.warning("NodeRAG indexing failed, falling back to exact matching only: %s", exc)
        return None


def build_documents(collection, graph) -> list[AbstractDocument]:
    pmid_edges = collect_pmid_edges(graph)
    documents: list[AbstractDocument] = []
    for article in collection.articles:
        pmid = str(article.pmid)
        entities = [
            {
                "name": str(annotation.name),
                "type": str(annotation.type),
                "mesh": str(annotation.mesh),
            }
            for annotation in article.annotations
        ]
        documents.append(
            AbstractDocument(
                pmid=pmid,
                title=str(article.title or f"PMID {pmid}"),
                abstract=str(article.abstract or "Abstract not available."),
                entities=entities,
                edges=pmid_edges.get(pmid, []),
                weight=1.0,
            )
        )
    return documents


def graph_retrieval_query(row: dict[str, str]) -> str:
    """Return a multilingual-safe query without consulting benchmark gold fields.

    The frozen PubMed query is already visible to every retrieval arm.  Appending
    its English biomedical terms gives NodeRAG lexical/embedding anchors for CJK
    questions while preserving the user's original question for answer generation.
    """
    question = row["question"].strip()
    if row.get("language", "").strip().casefold() not in {
        "traditional chinese",
        "simplified chinese",
        "chinese",
    }:
        return question
    pubmed_terms = re.sub(
        r"\b(?:and|or|not)\b|[()\[\]\"]", " ", row.get("pubmed_query", ""),
        flags=re.IGNORECASE,
    )
    pubmed_terms = " ".join(pubmed_terms.split())
    return f"{question} Biomedical retrieval terms: {pubmed_terms}" if pubmed_terms else question


def graph_preferences(
    graph_retriever: GraphRetriever, question: str
) -> tuple[str, list[dict[str, Any]], set[str]]:
    nodes = graph_retriever.find_relevant_nodes(question)
    context, paths = graph_retriever.get_subgraph_context_with_paths(
        nodes, query=question, max_hops=2
    )
    preferred: set[str] = set()
    for path in paths:
        for pmids in path.get("edge_pmids", []):
            preferred.update(str(pmid) for pmid in pmids)
    return context, paths, preferred


def _path_signature(path: dict[str, Any]) -> str:
    payload = {
        "names": path.get("names", []),
        "relations": path.get("relations", []),
        "edge_pmids": path.get("edge_pmids", []),
        "hop_count": path.get("hop_count"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _path_to_text(path: dict[str, Any]) -> str:
    names = path.get("names", [])
    relations = path.get("relations", [])
    flags = path.get("edge_is_directional", [])
    pieces = []
    for i in range(max(0, len(names) - 1)):
        arrow = "->" if i < len(flags) and flags[i] else "--"
        relation = relations[i] if i < len(relations) else "associated_with"
        pieces.append(f"{names[i]} {arrow}[{relation}] {names[i + 1]}")
    return " | ".join(pieces)


def _path_to_evidence_text(path: dict[str, Any]) -> str:
    """Format a graph path with the PMID and quote needed to audit every hop."""
    names = path.get("names", [])
    relations = path.get("relations", [])
    pmid_groups = path.get("edge_pmids", [])
    quote_groups = path.get("edge_evidence_quotes", [])
    gate_tier = path.get("gate_tier")
    gate_label = ""
    if gate_tier:
        usage = "CLAIM-SAFE" if path.get("claim_safe") else "RETRIEVAL-ONLY"
        gate_label = f" [GATE TIER {gate_tier}; {usage}]"
    value_class = path.get("incremental_value_class")
    value_label = f" [{str(value_class).upper().replace('_', '-')}]" if value_class else ""
    lines = [
        f"PATH {path.get('path_signature') or _path_signature(path)}{gate_label}{value_label} "
        f"(score={float(path.get('score', 0.0)):.3f})"
    ]
    for index in range(max(0, len(names) - 1)):
        relation = relations[index] if index < len(relations) else "associated_with"
        pmids = pmid_groups[index] if index < len(pmid_groups) else []
        quotes = quote_groups[index] if index < len(quote_groups) else []
        lines.append(
            f"  HOP {index + 1}: {names[index]} ->[{relation}] {names[index + 1]} "
            f"[PMIDs: {', '.join(str(pmid) for pmid in pmids) or 'none'}]"
        )
        for quote in quotes[:3]:
            compact_quote = " ".join(str(quote).split())[:400]
            lines.append(f'    EVIDENCE: "{compact_quote}"')
    return "\n".join(lines)


GENERIC_PATH_NODES = {
    "disease", "diseases", "cell", "cells", "protein", "proteins", "gene", "genes",
    "signaling", "pathway", "pathways", "process", "activity", "response", "effect",
}


def select_answer_paths(
    paths: list[dict[str, Any]], limit: int = 2, *, incremental_only: bool = True
) -> list[dict[str, Any]]:
    """Select a small, diverse claim-safe subset; retrieval may retain a much larger pool."""
    eligible = [
        path for path in paths
        if path.get("gate_tier") == "A" and path.get("claim_safe") is True
        and (
            not incremental_only
            or path.get("incremental_value_class") == "graph_incremental_candidate"
        )
    ]

    def priority(path: dict[str, Any]) -> tuple[Any, ...]:
        names = [str(name).strip().casefold() for name in path.get("names", [])]
        bridges = names[1:-1]
        generic_penalty = sum(
            name in GENERIC_PATH_NODES or len(name) <= 2 for name in bridges
        )
        cycle_penalty = len(names) - len(set(names))
        outside = len(path.get("supporting_pmids_outside_text_top_k", []))
        pmids = len(_collect_path_pmids([path]))
        incremental = path.get("incremental_value_class") == "graph_incremental_candidate"
        return (
            -int(incremental),
            -float(path.get("query_path_alignment_score", 0) or 0),
            -float(path.get("mechanism_utility_score", 0) or 0),
            generic_penalty, cycle_penalty, -outside, -pmids,
            int(path.get("candidate_rank") or 10**9), -float(path.get("score") or 0),
        )

    selected: list[dict[str, Any]] = []
    seen_evidence: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for path in sorted(eligible, key=priority):
        bridge_key = tuple(str(name).casefold() for name in path.get("names", [])[1:-1])
        pmid_key = tuple(sorted(_collect_path_pmids([path])))
        evidence_key = (bridge_key, pmid_key)
        if evidence_key in seen_evidence:
            continue
        selected.append(path)
        seen_evidence.add(evidence_key)
        if len(selected) >= limit:
            break
    return selected


def select_oracle_answer_paths(
    llm: LLMClient,
    paths: list[dict[str, Any]],
    question: str,
    *,
    limit: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Let a local model select from paths already accepted by the safety gate."""
    if getattr(llm, "provider", "") != "local":
        raise ValueError("Oracle path selection is restricted to provider=local")
    safety_eligible = select_answer_paths(
        paths, limit=max(len(paths), limit), incremental_only=False
    )
    alignment_eligible = [
        path
        for path in paths
        if float(path.get("query_endpoint_coverage", 1.0)) >= 1.0
        and float(path.get("requested_bridge_coverage", 1.0)) >= 1.0
    ]
    eligible = select_answer_paths(
        alignment_eligible,
        limit=max(len(alignment_eligible), limit),
        incremental_only=False,
    )
    if not eligible:
        return [], {
            "method": "local_oracle_query_aligned_v2",
            "safety_eligible": len(safety_eligible),
            "eligible": 0,
            "selected": [],
        }
    candidates = []
    signature_map: dict[str, dict[str, Any]] = {}
    for path in eligible:
        signature = str(path.get("path_signature") or _path_signature(path))
        signature_map[signature] = path
        candidates.append(
            {
                "id": signature,
                "nodes": path.get("names", []),
                "relations": path.get("relations", []),
                "pmids": sorted(_collect_path_pmids([path])),
                "incremental_class": path.get("incremental_value_class"),
                "mechanism_utility": path.get(
                    "mechanism_utility_score", path.get("score", 0)
                ),
            }
        )
    prompt = (
        "Select at most " + str(limit) + " graph paths that add the most useful, non-redundant "
        "mechanistic evidence for the question. Prefer cross-document, endpoint-aligned, "
        "incremental paths. Return JSON only: {\"selected_ids\":[\"id\"]}.\n\n"
        f"QUESTION:\n{question}\n\nCANDIDATES:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    raw_responses: list[str] = []
    requested: list[str] = []
    selected: list[dict[str, Any]] = []
    for _attempt in range(3):
        raw = llm.chat_completion_text(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a path-selection oracle for a blinded RAG ablation. Select only "
                        "IDs supplied by the user; do not add biomedical claims."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            timeout=300,
        )
        raw_responses.append(raw)
        match = re.search(r"\{.*\}", raw, flags=re.S)
        try:
            payload = json.loads(match.group(0) if match else raw)
        except (json.JSONDecodeError, AttributeError):
            payload = {}
        requested = payload.get("selected_ids", []) if isinstance(payload, dict) else []
        for signature in requested:
            path = signature_map.get(str(signature))
            if path is not None and path not in selected:
                selected.append(path)
            if len(selected) >= limit:
                break
        if selected:
            break
    if not selected:
        raise RuntimeError("Local oracle returned no valid safe path after 3 attempts")
    return selected, {
        "method": "local_oracle_query_aligned_v2",
        "safety_eligible": len(safety_eligible),
        "eligible": len(eligible),
        "requested": [str(item) for item in requested],
        "selected": [
            str(path.get("path_signature") or _path_signature(path)) for path in selected
        ],
        "raw_responses": raw_responses,
    }


def render_canonical_graph_insights(
    paths: list[dict[str, Any]], language: str
) -> str:
    """Render verifier-compatible graph claims without asking an LLM to copy hops."""
    if not paths:
        return ""
    title = "Graph-derived candidate insights" if language != "Traditional Chinese" else "圖譜衍生候選洞見"
    lines = [title]
    for path in paths:
        signature = path.get("path_signature") or _path_signature(path)
        value = path.get("incremental_value_class", "graph_confirmed")
        label = "GRAPH-INCREMENTAL CANDIDATE" if value == "graph_incremental_candidate" else "GRAPH-CONFIRMED"
        inference = "multi-hop inference" if len(path.get("relations", [])) > 1 else "direct graph evidence"
        clauses = []
        names = path.get("names", [])
        for index, relation in enumerate(path.get("relations", [])):
            pmids = path.get("edge_pmids", [])[index] if index < len(path.get("edge_pmids", [])) else []
            clauses.append(
                f"HOP {index + 1}: {names[index]} {relation} {names[index + 1]} "
                f"[PMID: {', '.join(str(pmid) for pmid in pmids)}]"
            )
        lines.append(f"- PATH {signature} — {label}; {inference}; " + "; ".join(clauses) + ".")
    return "\n".join(lines)


def render_natural_graph_insights(paths: list[dict[str, Any]], language: str) -> str:
    """Deterministically render safe paths as prose without graph/PATH notation."""
    if not paths:
        return ""
    if language == "Traditional Chinese":
        lines = ["補充證據整合："]
        for path in paths:
            clauses = []
            names = path.get("names", [])
            for index, relation in enumerate(path.get("relations", [])):
                if index + 1 >= len(names):
                    continue
                pmids = (
                    path.get("edge_pmids", [])[index]
                    if index < len(path.get("edge_pmids", []))
                    else []
                )
                relation_text = str(relation).replace("_", " ")
                clauses.append(
                    f"文獻支持 {names[index]} {relation_text} {names[index + 1]}"
                    f"（PMID: {', '.join(map(str, pmids)) or '無'}）"
                )
            if clauses:
                lines.append("；".join(clauses) + "。")
        lines.append("這些分段證據共同支持候選機制，但不代表單一研究已直接驗證完整鏈結。")
        return " ".join(lines)
    lines = ["Additional evidence synthesis:"]
    for path in paths:
        clauses = []
        names = path.get("names", [])
        for index, relation in enumerate(path.get("relations", [])):
            if index + 1 >= len(names):
                continue
            pmids = (
                path.get("edge_pmids", [])[index]
                if index < len(path.get("edge_pmids", []))
                else []
            )
            relation_text = str(relation).replace("_", " ")
            clauses.append(
                f"evidence supports that {names[index]} {relation_text} {names[index + 1]} "
                f"[PMID: {', '.join(map(str, pmids)) or 'none'}]"
            )
        if clauses:
            lines.append("; while ".join(clauses) + ".")
    lines.append(
        "This is a synthesis of evidence for individual hops, not proof that one study "
        "directly validated the complete chain."
    )
    return " ".join(lines)


def _collect_path_pmids(paths: list[dict[str, Any]]) -> set[str]:
    pmids: set[str] = set()
    for path in paths:
        for pmid_group in path.get("edge_pmids", []):
            pmids.update(str(pmid) for pmid in pmid_group)
    return pmids


def filter_frozen_paths_for_profile(
    paths: list[dict[str, Any]],
    profile_config: dict[str, Any],
    claim_confidence_threshold: float = GraphRetriever.DEFAULT_CLAIM_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Apply the live retrieval/evidence gate when replaying frozen paths."""
    filtered = []
    for path in paths:
        refreshed = dict(path)
        supports = refreshed.get("edge_supports", [])
        if supports:
            confidence_complete = all(
                support.get("selected_quote")
                and support.get("quote_relation_aligned")
                and support.get("selected_confidence") is not None
                and float(support["selected_confidence"])
                >= claim_confidence_threshold
                for support in supports
            )
            refreshed["edge_evidence_complete"] = [
                bool(
                    support.get("selected_quote")
                    and support.get("quote_relation_aligned")
                    and support.get("selected_confidence") is not None
                    and float(support["selected_confidence"])
                    >= claim_confidence_threshold
                )
                for support in supports
            ]
            if not confidence_complete:
                refreshed["claim_safe"] = False
                if refreshed.get("gate_tier") == "A":
                    refreshed["gate_tier"] = "B"
                refreshed.setdefault("gate_reasons", []).append(
                    f"frozen_confidence_below_{claim_confidence_threshold:g}"
                )
        if refreshed.get("retrieval_safe", True):
            filtered.append(refreshed)
    if profile_config.get("gate_evidence_paths"):
        filtered = [
            path
            for path in filtered
            if path.get("claim_safe", False)
            and path.get("edge_evidence_complete")
            and all(bool(flag) for flag in path.get("edge_evidence_complete", []))
        ]
    return filtered


def classify_incremental_path_value(
    paths: list[dict[str, Any]],
    traditional_ranking: list[tuple[str, float]],
    traditional_text_context: str,
    question: str,
) -> dict[str, Any]:
    """Contrast Tier A paths against the Text-RAG evidence exposure."""
    text_pmids = {str(pmid) for pmid, _score in traditional_ranking}
    comparison_text = " ".join(
        re.sub(r"[^\w]+", " ", traditional_text_context.casefold()).split()
    )
    normalized_question = " ".join(
        re.sub(r"[^\w]+", " ", question.casefold()).split()
    )
    through_match = re.search(
        r"\bthrough\s+(.+?)(?:\?|\.?\s+distinguish\b|$)", question, flags=re.I
    )
    requested_bridges = []
    if through_match:
        requested_bridges = [
            " ".join(re.sub(r"[^\w]+", " ", term.casefold()).split())
            for term in through_match.group(1).split(",")
            if term.strip()
        ]
        requested_bridges = list(dict.fromkeys(requested_bridges))

    def visible(term: str, text: str) -> bool:
        if not term:
            return False
        return term in text or (
            len(term.split()) >= 2 and set(term.split()) <= set(text.split())
        )
    incremental = 0
    confirmed = 0
    excluded = 0
    for path in paths:
        node_ids = path.get("node_ids", [])
        names = path.get("names", [])
        aliases = path.get("node_aliases", [])
        path_pmids = _collect_path_pmids([path])
        outside_pmids = sorted(path_pmids - text_pmids)
        multi_hop = 3 <= len(node_ids) <= 5
        bridge_terms: set[str] = set()
        if multi_hop and len(names) >= 2:
            bridge_terms.update(str(name) for name in names[1:-1])
            for alias_group in aliases[1:-1]:
                bridge_terms.update(str(alias) for alias in alias_group)
        normalized_bridge_terms = {
            " ".join(re.sub(r"[^\w]+", " ", term.casefold()).split())
            for term in bridge_terms
            if term
        }
        bridge_visible = any(
            len(term) >= 3 and visible(term, comparison_text)
            for term in normalized_bridge_terms
        )
        normalized_names = [
            " ".join(re.sub(r"[^\w]+", " ", str(name).casefold()).split())
            for name in names
        ]
        internal_terms = normalized_names[1:-1]
        requested_matches = [
            any(
                visible(requested, internal) or visible(internal, requested)
                for internal in internal_terms
            )
            for requested in requested_bridges
        ]
        requested_bridge_coverage = (
            sum(requested_matches) / len(requested_matches) if requested_matches else 1.0
        )
        bridge_precision = (
            sum(
                any(
                    visible(requested, internal) or visible(internal, requested)
                    for requested in requested_bridges
                )
                for internal in internal_terms
            ) / len(internal_terms)
            if internal_terms and requested_bridges
            else 1.0
        )
        endpoints = normalized_names[:1] + normalized_names[-1:]
        endpoint_coverage = (
            sum(visible(term, normalized_question) for term in endpoints) / 2
            if len(normalized_names) >= 2
            else 0.0
        )
        query_alignment = (
            0.4 * endpoint_coverage
            + 0.4 * requested_bridge_coverage
            + 0.2 * bridge_precision
            if requested_bridges
            else endpoint_coverage
        )
        claim_safe = bool(path.get("claim_safe"))
        # A bridge term can be visible in Text-RAG while the evidence needed to
        # compose the full two-hop relation is not.  Treat out-of-top-k hop
        # support as retrieval-incremental; retain bridge visibility as a
        # subtype instead of using it as a disqualifier.
        aligned = endpoint_coverage == 1.0 and requested_bridge_coverage == 1.0
        eligible = bool(claim_safe and multi_hop and outside_pmids and aligned)
        reasons = [
            "tier_a_claim_safe" if path.get("claim_safe") else "not_claim_safe",
            "two_hop" if len(node_ids) == 3 else "bounded_multi_hop" if multi_hop else "not_multi_hop",
            "support_outside_text_top_k" if outside_pmids else "all_support_in_text_top_k",
            "bridge_absent_from_text" if not bridge_visible else "bridge_visible_in_text",
            "query_path_aligned" if aligned else "query_path_misaligned",
        ]
        cross_document = len(path_pmids) >= 2
        graph_relevance = max(0.0, min(float(path.get("score") or 0.0), 1.0))
        relevance_score = 0.5 * graph_relevance + 0.5 * query_alignment
        incremental_score = (
            0.45 * float(bool(outside_pmids))
            + 0.25 * float(not bridge_visible)
            + 0.20 * float(cross_document)
            + 0.10 * float(multi_hop)
        )
        mechanism_utility = 0.55 * relevance_score + 0.45 * incremental_score
        if eligible:
            value_class = "graph_incremental_candidate"
            value_subtype = (
                "retrieval_incremental_bridge_visible"
                if bridge_visible
                else "retrieval_incremental_bridge_novel"
            )
        elif claim_safe:
            value_class = "graph_confirmed"
            value_subtype = "confirmation_only"
        else:
            value_class = "not_claim_safe"
            value_subtype = "excluded"
        path["incremental_value_class"] = value_class
        path["incremental_value_subtype"] = value_subtype
        path["incremental_value_reasons"] = reasons
        path["supporting_pmids_outside_text_top_k"] = outside_pmids
        path["path_relevance_score"] = round(relevance_score, 6)
        path["graph_relevance_score"] = round(graph_relevance, 6)
        path["query_endpoint_coverage"] = round(endpoint_coverage, 6)
        path["requested_bridge_coverage"] = round(requested_bridge_coverage, 6)
        path["query_bridge_precision"] = round(bridge_precision, 6)
        path["query_path_alignment_score"] = round(query_alignment, 6)
        path["incremental_mechanism_score"] = round(incremental_score, 6)
        path["mechanism_utility_score"] = round(mechanism_utility, 6)
        if eligible:
            incremental += 1
        elif claim_safe:
            confirmed += 1
        else:
            excluded += 1
    return {
        "method": "query_aligned_incremental_mechanism_value_v3",
        "graph_incremental_candidate_count": incremental,
        "graph_confirmed_count": confirmed,
        "not_claim_safe_count": excluded,
        "requirements": [
            "tier_a_claim_safe",
            "bounded_two_to_four_hop",
            "support_outside_text_top_k",
            "query_endpoint_and_requested_bridge_alignment",
        ],
        "requested_bridges": requested_bridges,
        "bridge_visibility_compares_text_context_not_question_text": True,
        "utility_formula": "0.55*path_relevance + 0.45*incremental_mechanism_value",
    }


def decide_hybrid_integration(paths: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose Traditional, citation-validation, or full Hybrid after path gating."""
    safe = [
        path
        for path in paths
        if path.get("gate_tier") == "A" and path.get("claim_safe") is True
    ]
    incremental = [
        path
        for path in safe
        if path.get("incremental_value_class") == "graph_incremental_candidate"
    ]
    if incremental:
        mode = "full_hybrid"
        reason = "claim_safe_incremental_path_available"
    elif safe:
        mode = "citation_validation"
        reason = "claim_safe_confirmation_only"
    else:
        mode = "traditional_fallback"
        reason = "no_claim_safe_path"
    return {
        "method": "three_stage_incremental_utility_router_v1",
        "mode": mode,
        "reason": reason,
        "claim_safe_path_count": len(safe),
        "incremental_path_count": len(incremental),
        "confirmatory_path_count": len(safe) - len(incremental),
        "citation_validation_pmids": sorted(_collect_path_pmids(safe)),
    }


def evidence_strength_by_pmid(paths: list[dict[str, Any]]) -> dict[str, float]:
    """Return each PMID's strongest fully evidenced, query-ranked path score."""
    strengths: dict[str, float] = {}
    for path in paths:
        if float(path.get("query_endpoint_coverage", 1.0) or 0) < 1.0:
            continue
        if float(path.get("requested_bridge_coverage", 1.0) or 0) < 1.0:
            continue
        if "claim_safe" in path and not path.get("claim_safe"):
            continue
        evidence_flags = path.get("edge_evidence_complete", [])
        if not evidence_flags or not all(bool(flag) for flag in evidence_flags):
            continue
        try:
            path_score = max(
                0.0,
                min(
                    float(path.get("mechanism_utility_score", path.get("score", 0.0))),
                    1.0,
                ),
            )
        except (TypeError, ValueError):
            continue
        for pmid in _collect_path_pmids([path]):
            strengths[pmid] = max(strengths.get(pmid, 0.0), path_score)
    return strengths


def rerank_with_evidence_gate(
    text_ranking: list[tuple[str, float]],
    paths: list[dict[str, Any]],
    *,
    top_k: int,
    min_graph_margin: float = 0.15,
    graph_blend: float = 0.35,
) -> tuple[list[tuple[str, float]], dict[str, Any]]:
    """Apply a conservative graph boost only when path evidence beats text by a margin.

    Path scores are query-ranked by GraphRetriever. Scores are capped at one and blended rather
    than multiplied, preventing the previous unconditional 1.5x boost from overwhelming the text
    ranking. Unsupported paths never contribute.
    """
    strengths = evidence_strength_by_pmid(paths)
    reranked: list[tuple[str, float]] = []
    boosted: dict[str, dict[str, float]] = {}
    for pmid, text_score in text_ranking:
        graph_score = strengths.get(pmid, 0.0)
        score = float(text_score)
        if graph_score >= score + min_graph_margin:
            score += graph_blend * (graph_score - score)
            boosted[pmid] = {
                "text_score": round(float(text_score), 6),
                "graph_score": round(graph_score, 6),
                "reranked_score": round(score, 6),
            }
        reranked.append((pmid, score))
    reranked.sort(key=lambda item: (-item[1], item[0]))
    return reranked[:top_k], {
        "method": "relevance_incremental_mechanism_blend_v1",
        "min_graph_margin": min_graph_margin,
        "graph_blend": graph_blend,
        "boosted_pmids": boosted,
    }


def _collect_node_pmids(graph, node_ids: list[str]) -> set[str]:
    pmids: set[str] = set()
    for node_id in node_ids:
        if graph.has_node(node_id):
            pmids.update(str(pmid) for pmid in graph.nodes[node_id].get("pmids", []))
    return pmids


def select_hybrid_exposure(
    profile: str,
    graph_retriever: GraphRetriever,
    graph,
    question: str,
    question_type: str = "",
) -> tuple[str, list[dict[str, Any]], set[str], dict[str, Any]]:
    if profile == "F_adaptive":
        routed_profile, route_reason = resolve_hybrid_profile(profile, question_type, question)
        context, paths, preferred_pmids, exposure = select_hybrid_exposure(
            routed_profile,
            graph_retriever,
            graph,
            question,
            question_type=question_type,
        )
        exposure.update(
            {
                "profile": "F_adaptive",
                "label": HYBRID_PROFILES["F_adaptive"]["label"],
                "routed_profile": routed_profile,
                "route_reason": route_reason,
                "question_type": question_type,
            }
        )
        return context, paths, preferred_pmids, exposure

    config = HYBRID_PROFILES.get(profile, HYBRID_PROFILES["legacy"])
    nodes = graph_retriever.find_relevant_nodes(question)
    if profile == "A_text_only":
        exposure = {
            "profile": profile,
            "label": config["label"],
            "use_node_rag": config["use_node_rag"],
            "max_hops": config["max_hops"],
            "gate_directional_paths": config["gate_directional_paths"],
            "gate_multi_document_paths": config["gate_multi_document_paths"],
            "node_ids": nodes,
            "exposed_pmids": [],
            "exposed_paths": [],
            "exposed_edges": [],
        }
        return "", [], set(), exposure

    if profile == "B_entity_validated":
        preferred_pmids = _collect_node_pmids(graph, nodes)
        exposure = {
            "profile": profile,
            "label": config["label"],
            "use_node_rag": config["use_node_rag"],
            "max_hops": config["max_hops"],
            "gate_directional_paths": config["gate_directional_paths"],
            "gate_multi_document_paths": config["gate_multi_document_paths"],
            "node_ids": nodes,
            "exposed_pmids": sorted(preferred_pmids),
            "exposed_paths": [],
            "exposed_edges": [],
        }
        return "", [], preferred_pmids, exposure

    max_hops = int(config["max_hops"])
    context, paths = graph_retriever.get_subgraph_context_with_paths(
        nodes, query=question, max_hops=max_hops
    )
    pre_gate_candidates = list(getattr(graph_retriever, "last_candidate_audit", paths))
    for candidate in pre_gate_candidates:
        candidate.setdefault("path_signature", _path_signature(candidate))
    gate_tier_counts = {
        tier: sum(path.get("gate_tier") == tier for path in paths) for tier in ("A", "B", "C")
    }
    rescue_triggered = any(bool(path.get("rescue_triggered")) for path in paths)
    rescue_added_paths = sum(bool(path.get("rescue_added")) for path in paths)
    rescue_outcomes = sorted(
        {str(path["rescue_outcome"]) for path in paths if path.get("rescue_outcome")}
    )
    paths = [path for path in paths if path.get("retrieval_safe", True)]
    for path in paths:
        path.setdefault("path_signature", _path_signature(path))
    if (
        config.get("gate_directional_paths")
        or config.get("gate_multi_document_paths")
        or config.get("gate_evidence_paths")
    ):
        filtered_paths: list[dict[str, Any]] = []
        for path in paths:
            edge_pmids = _collect_path_pmids([path])
            directional = bool(path.get("edge_is_directional")) and all(
                bool(flag) for flag in path.get("edge_is_directional", [])
            )
            if config["gate_directional_paths"] and not directional:
                continue
            if config["gate_multi_document_paths"] and len(edge_pmids) < 2:
                continue
            evidence_flags = path.get("edge_evidence_complete", [])
            if config.get("gate_evidence_paths") and (
                ("claim_safe" in path and not path.get("claim_safe"))
                or not evidence_flags
                or not all(bool(flag) for flag in evidence_flags)
            ):
                continue
            filtered_paths.append(path)
        paths = filtered_paths
    # Prefer the paths that best exercise Hybrid RAG without suppressing valid
    # single-study Tier-A support. Reports retain explicit hop/PMID counts so
    # direct evidence cannot be mistaken for cross-document discovery.
    paths.sort(
        key=lambda path: (
            -len(_collect_path_pmids([path])),
            -(len(path.get("node_ids", [])) - 1),
            int(path.get("candidate_rank") or 10**9),
        )
    )
    context = ""
    if paths:
        context_lines = [f"[HYBRID PROFILE: {config['label']}]"]
        context_lines.extend(_path_to_evidence_text(path) for path in paths[:10])
        context = "\n".join(context_lines)
    preferred_pmids = _collect_path_pmids(paths)
    exposure = {
        "profile": profile,
        "label": config["label"],
        "use_node_rag": config["use_node_rag"],
        "max_hops": config["max_hops"],
        "gate_directional_paths": config["gate_directional_paths"],
        "gate_multi_document_paths": config["gate_multi_document_paths"],
        "gate_evidence_paths": config.get("gate_evidence_paths", False),
        "gate_tier_counts": gate_tier_counts,
        "rescue_triggered": rescue_triggered,
        "rescue_added_paths": rescue_added_paths,
        "rescue_outcomes": rescue_outcomes,
        "pre_gate_candidate_count": len(pre_gate_candidates),
        "_pre_gate_candidates": pre_gate_candidates,
        "node_ids": nodes,
        "exposed_pmids": sorted(preferred_pmids),
        "exposed_paths": [path.get("names", []) for path in paths],
        "exposed_edges": [_path_to_text(path) for path in paths],
        "exposure_signature": hashlib.sha256(
            json.dumps(
                {
                    "profile": profile,
                    "paths": [_path_signature(path) for path in paths],
                    "pmids": sorted(preferred_pmids),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16],
    }
    return context, paths, preferred_pmids, exposure


def format_text_context(
    rag: AbstractRAG, ranking: list[tuple[str, float]]
) -> str:
    parts: list[str] = []
    for rank, (pmid, score) in enumerate(ranking, start=1):
        document = rag.documents[pmid]
        parts.append(
            "\n".join(
                [
                    f"Rank: {rank}",
                    f"PMID: {pmid}",
                    f"Retrieval score: {score:.6f}",
                    f"Title: {document.title}",
                    f"Abstract: {document.abstract}",
                ]
            )
        )
    return "\n\n---\n\n".join(parts)


def generate_answer(
    llm: LLMClient,
    *,
    system: str,
    question: str,
    language: str,
    text_context: str = "",
    graph_context: str = "",
    answer_paths: list[dict[str, Any]] | None = None,
    graph_answer_style: str = "canonical",
    max_tokens: int = 1600,
) -> str:
    if system == "general_llm":
        instruction = (
            "Answer the biomedical question using only your pretrained knowledge. "
            "Do not claim to have searched PubMed. Do not fabricate PMIDs or citations. "
            "Distinguish established evidence from uncertainty and hypothesis."
        )
        user_content = question
    else:
        arm = (
            "NetMedEx Hybrid RAG with graph-guided retrieval"
            if system == "netmedex_hybrid_rag"
            else "traditional text-only RAG"
        )
        instruction = (
            f"You are the {arm} evaluation arm. Answer only from the supplied context. "
            "Cite supporting records inline as [PMID: number]. Separate direct evidence, "
            "association, and testable hypothesis. Label human versus animal or in-vitro "
                "evidence when the context permits. If evidence is absent, say so. "
                "Be concise and prioritize the evidence most relevant to the question."
        )
        if system == "netmedex_hybrid_rag" and graph_context:
            instruction += (
                " A deterministic, evidence-checked mechanism note will be appended after your "
                "answer. Do not write PATH identifiers or a graph-insights section yourself, and "
                "do not infer additional mechanisms from graph paths in the narrative."
            )
        elif system == "netmedex_hybrid_rag":
            instruction += (
                " No graph paths were supplied. Do not create PATH identifiers or a "
                "'Graph-derived candidate insights' section; answer from PubMed context only."
            )
        user_content = (
            f"QUESTION:\n{question}\n\nPUBMED CONTEXT:\n{text_context}"
        )
        # The graph is deliberately not exposed as free-form generation context.  Its selected
        # claims are appended below by a deterministic hop-complete renderer.

    language_instruction = (
        "Respond entirely in Traditional Chinese."
        if language == "Traditional Chinese"
        else "Respond entirely in English."
    )
    compact_for_appendix = bool(graph_context and graph_answer_style == "canonical")
    length_instruction = (
        f"Your narrative must be at most {'650' if compact_for_appendix else '1,000'} Chinese characters, use no tables, "
        "use at most five bullets, and end with one short conclusion sentence."
        if language == "Traditional Chinese"
        else f"Your narrative must be at most {'300' if compact_for_appendix else '450'} words, use no tables, use at most "
        "five bullets, and end with one short conclusion sentence."
    )
    messages = [
        {
            "role": "system",
            "content": f"{instruction} {language_instruction} {length_instruction}",
        },
        {"role": "user", "content": user_content},
    ]
    answer = ""
    attempted_limits = []
    for token_limit in (max_tokens, min(max_tokens * 2, 6000)):
        if token_limit in attempted_limits:
            continue
        attempted_limits.append(token_limit)
        answer = llm.chat_completion_text(
            messages=messages,
            temperature=1.0,
            max_tokens=token_limit,
            timeout=300,
        )
        finish_reason = str(
            getattr(llm, "last_completion_finish_reason", "") or ""
        ).lower()
        if finish_reason not in {"length", "max_tokens"}:
            break
        LOGGER.warning(
            "Answer generation reached token limit %s; retrying with a larger limit",
            token_limit,
        )
    else:
        raise RuntimeError(
            f"Answer generation remained truncated after token limits {attempted_limits}"
        )
    graph_insights = (
        render_natural_graph_insights(answer_paths or [], language)
        if graph_answer_style == "natural"
        else render_canonical_graph_insights(answer_paths or [], language)
    )
    return f"{answer.rstrip()}\n\n{graph_insights}" if graph_insights else answer


def run_question(
    row: dict[str, str],
    *,
    llm: LLMClient,
    max_articles: int,
    top_k: int,
    semantic_threshold: float,
    claim_confidence_threshold: float,
    hybrid_profile: str,
    question_dir: Path,
    systems: tuple[str, ...] = SYSTEMS,
    reuse_corpora_dir: Path | None = None,
    reuse_exposures_dir: Path | None = None,
    reuse_graphs_dir: Path | None = None,
    graph_cache_dir: Path | None = None,
    persist_graph: bool = False,
    generate_answers: bool = True,
    kg_expansion_articles: int = 0,
    suppress_graph_answer_context: bool = False,
    integration_policy: str = "legacy",
    answer_path_policy: str = "incremental",
    graph_answer_style: str = "canonical",
    enable_kg_reranking: bool = True,
    fallback_answers_dir: Path | None = None,
    answer_max_tokens: int = 1600,
) -> dict[str, Any]:
    started = time.monotonic()
    usage_before = dict(getattr(llm, "completion_usage_totals", {}) or {})
    question_id = row["question_id"]
    frozen_corpus = (
        reuse_corpora_dir / question_id / "corpus.pubtator" if reuse_corpora_dir else None
    )
    if frozen_corpus is not None:
        if not frozen_corpus.exists():
            raise FileNotFoundError(f"Frozen replay corpus not found: {frozen_corpus}")
        collection = PubTatorIO.parse(frozen_corpus)
        pmids = [str(article.pmid) for article in collection.articles]
        effective_query = row["pubmed_query"]
        query_attempts = ["[reused frozen corpus]"]
        fetch_seconds = 0.0
    else:
        pmids, effective_query, query_attempts = pubmed_esearch_with_relaxation(
            row["pubmed_query"], max_articles
        )
        if not pmids:
            raise RuntimeError(
                f"PubMed returned no PMIDs after {len(query_attempts)} query attempts"
            )
        fetch_started = time.monotonic()
        collection = PubTatorAPI(
            query=None,
            pmid_list=pmids,
            sort="score",
            request_format="biocjson",
            max_articles=max_articles,
            full_text=False,
            queue=None,
        ).run()
        fetch_seconds = time.monotonic() - fetch_started
    (question_dir / "corpus.pubtator").write_text(
        collection.to_pubtator_str(annotation_use_identifier_name=True),
        encoding="utf-8",
    )
    atomic_json(
        question_dir / "corpus_manifest.json",
        {
            "question_id": question_id,
            "pubmed_query": row["pubmed_query"],
            "effective_pubmed_query": effective_query,
            "query_attempts": query_attempts,
            "esearch_pmids": pmids,
            "fetched_pmids": [str(article.pmid) for article in collection.articles],
        },
    )

    routed_profile, _route_reason = resolve_hybrid_profile(
        hybrid_profile, row.get("question_type", ""), row["question"]
    )
    profile_config = HYBRID_PROFILES.get(routed_profile, HYBRID_PROFILES["legacy"])

    frozen_exposure_result = None
    if reuse_exposures_dir is not None and routed_profile != "A_text_only":
        frozen_exposure_path = reuse_exposures_dir / question_id / "result.json"
        if not frozen_exposure_path.exists():
            raise FileNotFoundError(f"Frozen graph exposure not found: {frozen_exposure_path}")
        frozen_exposure_result = json.loads(frozen_exposure_path.read_text(encoding="utf-8"))
        frozen_route = frozen_exposure_result.get("evidence_exposure", {}).get(
            "routed_profile",
            frozen_exposure_result.get("evidence_exposure", {}).get("profile"),
        )
        if frozen_route != routed_profile:
            raise ValueError(
                f"Frozen exposure route mismatch for {question_id}: "
                f"expected {routed_profile}, found {frozen_route}"
            )

    graph_started = time.monotonic()
    graph_cache_hit = False
    graph_cache_key = ""
    frozen_graph_path = (
        reuse_graphs_dir / question_id / "graph.pkl" if reuse_graphs_dir else None
    )
    if routed_profile == "A_text_only":
        # A true adaptive text-only decision must not pay to build a semantic graph that will
        # never be exposed. This is both the deployable behavior and the fair cost/latency arm.
        graph = nx.Graph()
    elif frozen_exposure_result is not None:
        # A query-specific frozen exposure contains the exact ranked paths needed for replay.
        # Avoid regenerating a stochastic semantic graph or paying its completion-token cost.
        graph = nx.Graph()
    elif frozen_graph_path is not None:
        if not frozen_graph_path.exists():
            raise FileNotFoundError(f"Frozen replay graph not found: {frozen_graph_path}")
        # Explicit opt-in only: pickle replay is limited to locally frozen evaluation artifacts.
        with frozen_graph_path.open("rb") as handle:
            graph = pickle.load(handle)
        if not isinstance(graph, nx.Graph):
            raise TypeError(f"Frozen graph has unexpected type: {type(graph)!r}")
    else:
        cache = PersistentGraphCache(graph_cache_dir) if graph_cache_dir else None
        cache_config = {
            "edge_method": "semantic",
            "semantic_threshold": semantic_threshold,
            "node_type": "all",
            "model": str(getattr(llm, "model", "")),
        }
        corpus_bytes = (question_dir / "corpus.pubtator").read_bytes()
        if cache is not None:
            graph_cache_key = cache.key(corpus_bytes, cache_config)
            graph = cache.load(graph_cache_key)
            graph_cache_hit = graph is not None
        else:
            graph = None
        if graph is None:
            graph_builder = PubTatorGraphBuilder(
                node_type="all",
                edge_method="semantic",
                llm_client=llm,
                semantic_threshold=semantic_threshold,
            )
            graph_builder.add_collection(collection)
            graph = graph_builder.build(
                pmid_weights=None,
                weighting_method="freq",
                edge_weight_cutoff=1,
                community=False,
                max_edges=0,
            )
        # Semantic extraction failures are logged per PMID by the builder. If
        # every request fails, the builder still returns an empty NetworkX
        # graph; treating that as a successful Hybrid result would turn an API
        # outage into a false negative. Fail closed so the outer run manifest
        # records the question as failed and the result cannot enter an eval.
            require_nonempty_semantic_graph(graph, len(collection.articles))
            if cache is not None:
                cache.store(graph_cache_key, graph, cache_config)
    if persist_graph and graph.number_of_nodes() > 0:
        graph_path = question_dir / "graph.pkl"
        temporary_graph_path = graph_path.with_suffix(".pkl.tmp")
        with temporary_graph_path.open("wb") as handle:
            pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
        temporary_graph_path.replace(graph_path)
    graph_seconds = time.monotonic() - graph_started

    documents = build_documents(collection, graph)
    initial_document_pmids = {document.pmid for document in documents}
    index_started = time.monotonic()
    rag = AbstractRAG(llm, collection_name=f"formal_{question_id.lower()}")
    rag.index_abstracts(documents)
    index_seconds = time.monotonic() - index_started

    text_candidates = rag.search(row["question"], top_k=len(documents))
    traditional_ranking = text_candidates[:top_k]
    if frozen_exposure_result is not None:
        frozen_graph = frozen_exposure_result.get("graph", {})
        frozen_paths = list(frozen_graph.get("paths", []))
        pre_gate_candidates = filter_frozen_paths_for_profile(
            list(frozen_graph.get("pre_gate_candidates", frozen_paths)),
            {"gate_evidence_paths": False},
            claim_confidence_threshold=claim_confidence_threshold,
        )
        paths = filter_frozen_paths_for_profile(
            frozen_paths,
            profile_config,
            claim_confidence_threshold=claim_confidence_threshold,
        )
        exposure = dict(frozen_exposure_result.get("evidence_exposure", {}))
        exposure["frozen_exposure_source"] = str(
            reuse_exposures_dir / question_id / "result.json"
        )
        preferred_pmids = _collect_path_pmids(paths)
        exposure["frozen_candidate_path_count"] = len(frozen_paths)
        exposure["frozen_exposed_path_count"] = len(paths)
        exposure["exposed_pmids"] = sorted(preferred_pmids)
        exposure["exposed_paths"] = [path.get("names", []) for path in paths]
        exposure["exposed_edges"] = [_path_to_text(path) for path in paths]
        graph_context = ""
        if paths:
            graph_context = "\n".join(
                [
                    f"[HYBRID PROFILE: {profile_config['label']}]",
                    *(_path_to_evidence_text(path) for path in paths[:10]),
                ]
            )
        graph_counts = {
            "node_count": int(frozen_graph.get("node_count", 0)),
            "edge_count": int(frozen_graph.get("edge_count", 0)),
        }
    else:
        graph_node_rag = (
            # NodeRAG resets its Chroma collection while indexing. Keep it separate from
            # the abstract collection or the subsequent document search returns node IDs.
            build_node_rag(llm, graph, collection_name=f"formal_{question_id.lower()}_nodes")
            if profile_config["use_node_rag"]
            else None
        )
        graph_retriever = GraphRetriever(
            graph,
            node_rag=graph_node_rag if graph_node_rag else None,
            claim_confidence_threshold=claim_confidence_threshold,
        )
        graph_query = graph_retrieval_query(row)
        graph_context, paths, preferred_pmids, exposure = select_hybrid_exposure(
            hybrid_profile,
            graph_retriever,
            graph,
            graph_query,
            question_type=row.get("question_type", ""),
        )
        exposure["graph_retrieval_query"] = graph_query
        graph_counts = {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        }
        pre_gate_candidates = list(exposure.pop("_pre_gate_candidates", []))
    exposure["claim_confidence_threshold"] = claim_confidence_threshold
    traditional_text_context = format_text_context(rag, traditional_ranking)
    incremental_audit = classify_incremental_path_value(
        paths, traditional_ranking, traditional_text_context, row["question"]
    )
    exposure["incremental_value"] = incremental_audit
    exposure["pre_gate_incremental_value"] = classify_incremental_path_value(
        pre_gate_candidates,
        traditional_ranking,
        traditional_text_context,
        row["question"],
    )
    integration = decide_hybrid_integration(paths)
    integration["policy"] = integration_policy
    exposure["integration_decision"] = integration
    full_hybrid_enabled = (
        integration_policy != "three_stage" or integration["mode"] == "full_hybrid"
    )
    # Discard the broad retrieval exposure assembled above. Only explicitly selected answer
    # paths may influence answer length or rendering after the three-stage decision.
    graph_context = ""
    answer_paths: list[dict[str, Any]] = []
    oracle_audit: dict[str, Any] = {}
    if paths and full_hybrid_enabled:
        if answer_path_policy == "all_safe":
            answer_paths = select_answer_paths(
                paths, limit=min(10, len(paths)), incremental_only=False
            )
        elif answer_path_policy == "local_oracle":
            answer_paths, oracle_audit = select_oracle_answer_paths(
                llm, paths, row["question"], limit=2
            )
        else:
            answer_paths = select_answer_paths(paths, limit=2, incremental_only=True)
        exposure["answer_path_policy"] = answer_path_policy
        exposure["oracle_path_selection"] = oracle_audit
        exposure["answer_fallback_to_reranked_text"] = not answer_paths
        graph_context = "\n".join(
            [
                f"[HYBRID PROFILE: {profile_config['label']}]",
                *(_path_to_evidence_text(path) for path in answer_paths),
            ]
        )
        exposure["answer_context_path_signatures"] = [
            path.get("path_signature") or _path_signature(path)
            for path in answer_paths
        ]

    expansion_started = time.monotonic()
    expansion_paths = filter_expansion_paths(pre_gate_candidates)
    expansion_queries = build_pubmed_expansion_queries(expansion_paths)
    expansion_pmids: list[str] = []
    hybrid_candidates = text_candidates
    expansion_merge_audit: dict[str, Any] = {
        "method": "disabled",
        "accepted_added_pmids": [],
    }
    expansion_enabled = kg_expansion_articles > 0 and full_hybrid_enabled
    if expansion_enabled and expansion_queries:
        existing_pmids = set(rag.documents)
        for expansion_query in expansion_queries:
            for pmid in pubmed_esearch(expansion_query, kg_expansion_articles):
                if pmid not in existing_pmids and pmid not in expansion_pmids:
                    expansion_pmids.append(pmid)
                if len(expansion_pmids) >= kg_expansion_articles:
                    break
            if len(expansion_pmids) >= kg_expansion_articles:
                break
        if expansion_pmids:
            expanded_collection = PubTatorAPI(
                query=None,
                pmid_list=expansion_pmids,
                sort="score",
                request_format="biocjson",
                max_articles=len(expansion_pmids),
                full_text=False,
                queue=None,
            ).run()
            expanded_documents = build_documents(expanded_collection, nx.Graph())
            seen_documents = {document.pmid for document in documents}
            documents.extend(
                document
                for document in expanded_documents
                if document.pmid not in seen_documents
            )
            # Re-index the bounded union once; the Traditional arm retains its frozen
            # first-stage ranking, while the KG arm may retrieve the added documents.
            rag.index_abstracts(documents)
            expanded_ranking = rag.search(row["question"], top_k=len(documents))
            hybrid_candidates, expansion_merge_audit = merge_expanded_ranking(
                text_candidates,
                expanded_ranking,
                expansion_pmids,
                top_k=top_k,
            )
    expansion_seconds = time.monotonic() - expansion_started
    exposure["kg_expansion"] = {
        "enabled": expansion_enabled,
        "candidate_path_count": len(expansion_paths),
        "queries": expansion_queries,
        "added_pmids": expansion_pmids,
        "added_document_count": len(set(rag.documents) - initial_document_pmids),
        "merge": expansion_merge_audit,
    }

    if enable_kg_reranking and full_hybrid_enabled:
        hybrid_ranking, rerank_audit = rerank_with_evidence_gate(
            hybrid_candidates, paths, top_k=top_k
        )
    else:
        hybrid_ranking = hybrid_candidates[:top_k] if full_hybrid_enabled else traditional_ranking
        rerank_audit = {
            "method": "disabled",
            "reason": (
                "configuration"
                if full_hybrid_enabled
                else f"integration_mode={integration['mode']}"
            ),
            "boosted_pmids": {},
        }
    exposure["reranking"] = rerank_audit

    answers: dict[str, str] = {}
    answer_seconds: dict[str, float] = {}
    answer_finish_reasons: dict[str, str] = {}
    generation_specs = (
        (
            "netmedex_hybrid_rag",
            hybrid_ranking,
            "" if suppress_graph_answer_context else graph_context,
        ),
        ("traditional_rag", traditional_ranking, ""),
        ("general_llm", [], ""),
    )
    for system, ranking, current_graph_context in generation_specs:
        if system not in systems:
            continue
        if not generate_answers:
            continue
        answer_started = time.monotonic()
        if (
            system == "netmedex_hybrid_rag"
            and not full_hybrid_enabled
            and fallback_answers_dir is not None
        ):
            fallback_path = fallback_answers_dir / question_id / "result.json"
            if not fallback_path.exists():
                raise FileNotFoundError(f"Traditional fallback answer not found: {fallback_path}")
            fallback_result = json.loads(fallback_path.read_text(encoding="utf-8"))
            answer = str(
                fallback_result.get("answers", {}).get("traditional_rag", "")
            ).strip()
            if not answer:
                raise ValueError(f"Traditional fallback answer is blank: {fallback_path}")
            answers[system] = answer
            answer_seconds[system] = 0.0
            answer_finish_reasons[system] = "reused_fallback"
            exposure["fallback_answer_reused"] = {
                "source": str(fallback_path),
                "source_system": "traditional_rag",
                "mode": integration["mode"],
            }
            continue
        answer = ""
        for attempt in range(1, 4):
            answer = generate_answer(
                llm,
                system=system,
                question=row["question"],
                language=row["language"],
                text_context=format_text_context(rag, ranking) if ranking else "",
                graph_context=current_graph_context,
                answer_paths=(answer_paths if current_graph_context else []),
                graph_answer_style=graph_answer_style,
                max_tokens=answer_max_tokens,
            )
            if system == "netmedex_hybrid_rag":
                trial_verification = verify_answer_graph_claims(answer, paths)
                if trial_verification.get("unsupported_claim_count", 0):
                    LOGGER.warning(
                        "%s generated unsupported PATH syntax for %s (attempt %s/3); retrying",
                        system,
                        question_id,
                        attempt,
                    )
                    answer = ""
                    continue
            if answer.strip():
                break
            LOGGER.warning(
                "%s returned an empty answer for %s (attempt %s/3)",
                system,
                question_id,
                attempt,
            )
        if not answer.strip():
            raise RuntimeError(f"{system} returned an empty answer after 3 attempts")
        answers[system] = answer
        answer_seconds[system] = time.monotonic() - answer_started
        answer_finish_reasons[system] = str(
            getattr(llm, "last_completion_finish_reason", "") or "unknown"
        )

    usage_after = dict(getattr(llm, "completion_usage_totals", {}) or {})
    token_usage = {
        field: usage_after.get(field, 0) - usage_before.get(field, 0)
        for field in set(usage_before) | set(usage_after)
    }
    claim_verification = {}
    if "netmedex_hybrid_rag" in answers:
        claim_verification = verify_answer_graph_claims(
            answers["netmedex_hybrid_rag"], paths
        )
        if claim_verification.get("unsupported_claim_count", 0):
            raise RuntimeError("Fail-closed graph answer contained an unsupported PATH claim")
    return {
        "status": "complete",
        "question_id": question_id,
        "domain": row["domain"],
        "question": row["question"],
        "question_type": row.get("question_type", ""),
        "pubmed_query": row["pubmed_query"],
        "effective_pubmed_query": effective_query,
        "query_attempts": query_attempts,
        "language": row["language"],
        "corpus_pmids": [str(article.pmid) for article in collection.articles],
        "graph": {
            **graph_counts,
            "cache_hit": graph_cache_hit,
            "cache_key": graph_cache_key,
            "path_count": len(paths),
            "pre_gate_candidate_count": len(pre_gate_candidates),
            "pre_gate_candidates": pre_gate_candidates,
            "preferred_pmids": sorted(preferred_pmids),
            "paths": [
                {
                    "path_id": f"{question_id}-P{index:02d}",
                    "path_signature": path.get("path_signature") or _path_signature(path),
                    "path_text": _path_to_text(path),
                    "node_ids": path.get("node_ids", []),
                    "names": path.get("names", []),
                    "node_aliases": path.get("node_aliases", []),
                    "relations": path.get("relations", []),
                    "edge_pmids": path.get("edge_pmids", []),
                    "edge_is_directional": path.get("edge_is_directional", []),
                    "edge_evidence_quotes": path.get("edge_evidence_quotes", []),
                    "edge_evidence_complete": path.get("edge_evidence_complete", []),
                    "edge_supports": path.get("edge_supports", []),
                    "gate_tier": path.get("gate_tier"),
                    "gate_reasons": path.get("gate_reasons", []),
                    "claim_safe": path.get("claim_safe", False),
                    "retrieval_safe": path.get("retrieval_safe", False),
                    "candidate_rank": path.get("candidate_rank"),
                    "rescue_triggered": path.get("rescue_triggered", False),
                    "rescue_added": path.get("rescue_added", False),
                    "rescue_outcome": path.get("rescue_outcome"),
                    "diversity_added": path.get("diversity_added", False),
                    "incremental_value_class": path.get("incremental_value_class"),
                    "incremental_value_subtype": path.get(
                        "incremental_value_subtype"
                    ),
                    "incremental_value_reasons": path.get(
                        "incremental_value_reasons", []
                    ),
                    "supporting_pmids_outside_text_top_k": path.get(
                        "supporting_pmids_outside_text_top_k", []
                    ),
                    "path_relevance_score": path.get("path_relevance_score"),
                    "graph_relevance_score": path.get("graph_relevance_score"),
                    "query_endpoint_coverage": path.get("query_endpoint_coverage"),
                    "requested_bridge_coverage": path.get("requested_bridge_coverage"),
                    "query_bridge_precision": path.get("query_bridge_precision"),
                    "query_path_alignment_score": path.get(
                        "query_path_alignment_score"
                    ),
                    "incremental_mechanism_score": path.get(
                        "incremental_mechanism_score"
                    ),
                    "mechanism_utility_score": path.get("mechanism_utility_score"),
                    "score": path.get("score"),
                    "hop_count": path.get("hop_count"),
                }
                for index, path in enumerate(paths, start=1)
            ],
        },
        "evidence_exposure": exposure,
        "rankings": {
            "netmedex_hybrid_rag": [
                {"pmid": pmid, "score": score} for pmid, score in hybrid_ranking
            ],
            "traditional_rag": [
                {"pmid": pmid, "score": score} for pmid, score in traditional_ranking
            ],
        },
        "answers": answers,
        "answer_finish_reasons": answer_finish_reasons,
        "claim_verification": claim_verification,
        "timings_seconds": {
            "pubtator_fetch": fetch_seconds,
            "semantic_graph": graph_seconds,
            "vector_index": index_seconds,
            "kg_expansion": expansion_seconds,
            **{f"answer_{key}": value for key, value in answer_seconds.items()},
            "total": time.monotonic() - started,
        },
        "token_usage": token_usage,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def compile_outputs(
    run_dir: Path,
    queries: list[dict[str, str]],
    run_id: str,
    systems: tuple[str, ...] = SYSTEMS,
    require_answers: bool = True,
) -> tuple[int, int]:
    retrieval_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    exposure_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, str]] = []
    claim_verification_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []
    complete = 0
    failed = 0

    for row in queries:
        checkpoint = run_dir / "questions" / row["question_id"] / "result.json"
        if not checkpoint.exists():
            continue
        result = json.loads(checkpoint.read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            failed += 1
            continue
        answers = result.get("answers", {})
        if require_answers and any(
            not str(answers.get(system, "")).strip() for system in systems
        ):
            failed += 1
            continue
        rankings = result.get("rankings", {})
        if any(system not in rankings for system in SYSTEMS[:2]):
            failed += 1
            continue
        complete += 1
        verification = result.get("claim_verification", {}) or {}
        verification_claims = verification.get("claims", [])
        if verification_claims:
            for claim in verification_claims:
                claim_verification_rows.append(
                    {
                        "question_id": row["question_id"],
                        "run_id": run_id,
                        "claim_id": claim.get("claim_id", ""),
                        "path_id": claim.get("path_id", ""),
                        "verdict": claim.get("verdict", ""),
                        "reasons": ";".join(claim.get("reasons", [])),
                    }
                )
        elif verification:
            claim_verification_rows.append(
                {
                    "question_id": row["question_id"],
                    "run_id": run_id,
                    "claim_id": "",
                    "path_id": "",
                    "verdict": "no_path_citation",
                    "reasons": "no_path_citations_detected",
                }
            )
        graph = result.get("graph", {})
        exposure = result.get("evidence_exposure", {})
        for system, ranking in rankings.items():
            for rank, item in enumerate(ranking, start=1):
                retrieval_rows.append(
                    {
                        "system": system,
                        "question_id": row["question_id"],
                        "rank": rank,
                        "pmid": item["pmid"],
                        "score": f"{float(item['score']):.8f}",
                    }
                )
        for path_rank, path in enumerate(graph.get("paths", []), start=1):
            names = path.get("names", [])
            relations = path.get("relations", [])
            edge_pmids = path.get("edge_pmids", [])
            edge_is_directional = path.get("edge_is_directional", [])
            path_rows.append(
                {
                    "system": "netmedex_hybrid_rag",
                    "arm": exposure.get("profile", "legacy"),
                    "question_id": row["question_id"],
                    "run_id": run_id,
                    "path_rank": path_rank,
                    "path_id": path.get("path_id", f"{row['question_id']}-P{path_rank:02d}"),
                    "path_signature": path.get("path_signature", ""),
                    "source": names[0] if len(names) >= 1 else "",
                    "bridge": names[1] if len(names) >= 3 else "",
                    "target": names[-1] if names else "",
                    "relation_1": relations[0] if len(relations) >= 1 else "",
                    "relation_2": relations[1] if len(relations) >= 2 else "",
                    "direction_1": "forward" if len(edge_is_directional) >= 1 and edge_is_directional[0] else "undirected",
                    "direction_2": "forward" if len(edge_is_directional) >= 2 and edge_is_directional[1] else "undirected",
                    "pmids": ";".join(sorted({pmid for group in edge_pmids for pmid in group})),
                    "score": f"{float(path.get('score', 0.0)):.4f}",
                    "hop_count": path.get("hop_count", len(names) - 1),
                    "path_text": path.get("path_text", ""),
                }
            )
        if exposure:
            exposure_rows.append(
                {
                    "system": "netmedex_hybrid_rag",
                    "arm": exposure.get("profile", "legacy"),
                    "question_id": row["question_id"],
                    "run_id": run_id,
                    "label": exposure.get("label", ""),
                    "question_type": exposure.get("question_type", row.get("question_type", "")),
                    "routed_profile": exposure.get("routed_profile", exposure.get("profile", "")),
                    "route_reason": exposure.get("route_reason", "fixed profile"),
                    "use_node_rag": exposure.get("use_node_rag", ""),
                    "max_hops": exposure.get("max_hops", ""),
                    "gate_directional_paths": exposure.get("gate_directional_paths", ""),
                    "gate_multi_document_paths": exposure.get("gate_multi_document_paths", ""),
                    "gate_evidence_paths": exposure.get("gate_evidence_paths", ""),
                    "node_ids": ";".join(exposure.get("node_ids", [])),
                    "exposed_pmids": ";".join(exposure.get("exposed_pmids", [])),
                    "exposed_edges": ";".join(exposure.get("exposed_edges", [])),
                    "exposed_paths": ";".join(
                        "|".join(path) if isinstance(path, list) else str(path)
                        for path in exposure.get("exposed_paths", [])
                    ),
                    "exposure_signature": exposure.get("exposure_signature", ""),
                }
            )
        for system in systems:
            if system not in answers:
                continue
            output_rows.append(
                {
                    "system": system,
                    "question_id": row["question_id"],
                    "run_id": run_id,
                    "output_source": "fixed_formal_system_run",
                    "answer": answers[system],
                }
            )
        timing_rows.append(
            {
                "question_id": row["question_id"],
                **result["timings_seconds"],
                **result["graph"],
                "corpus_document_count": len(result["corpus_pmids"]),
                **{
                    f"tokens_{field}": value
                    for field, value in result.get("token_usage", {}).items()
                },
            }
        )

    with (run_dir / "retrieval_runs.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["system", "question_id", "rank", "pmid", "score"]
        )
        writer.writeheader()
        writer.writerows(retrieval_rows)

    with (run_dir / "path_runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "system",
                "arm",
                "question_id",
                "run_id",
                "path_rank",
                "path_id",
                "path_signature",
                "source",
                "bridge",
                "target",
                "relation_1",
                "relation_2",
                "direction_1",
                "direction_2",
                "pmids",
                "score",
                "hop_count",
                "path_text",
            ],
        )
        writer.writeheader()
        writer.writerows(path_rows)

    with (run_dir / "evidence_exposure.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "system",
                "arm",
                "question_id",
                "run_id",
                "label",
                "question_type",
                "routed_profile",
                "route_reason",
                "use_node_rag",
                "max_hops",
                "gate_directional_paths",
                "gate_multi_document_paths",
                "gate_evidence_paths",
                "node_ids",
                "exposed_pmids",
                "exposed_edges",
                "exposed_paths",
                "exposure_signature",
            ],
        )
        writer.writeheader()
        writer.writerows(exposure_rows)

    with (run_dir / "system_outputs.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["system", "question_id", "run_id", "output_source", "answer"],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    with (run_dir / "claim_verification.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["question_id", "run_id", "claim_id", "path_id", "verdict", "reasons"],
        )
        writer.writeheader()
        writer.writerows(claim_verification_rows)

    timing_fields = [
        "question_id",
        "pubtator_fetch",
        "semantic_graph",
        "vector_index",
        "kg_expansion",
        "answer_netmedex_hybrid_rag",
        "answer_traditional_rag",
        "answer_general_llm",
        "total",
        "node_count",
        "edge_count",
        "path_count",
        "preferred_pmids",
        "corpus_document_count",
        "tokens_input_tokens",
        "tokens_output_tokens",
        "tokens_total_tokens",
    ]
    with (run_dir / "run_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=timing_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(timing_rows)
    return complete, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries", type=Path, default=Path("evaluation/formal/formal_run_queries.csv")
    )
    parser.add_argument(
        "--expected-question-count",
        type=int,
        default=50,
        help="Expected unique row count in --queries; retain 50 for the formal benchmark.",
    )
    parser.add_argument(
        "--questions-metadata",
        type=Path,
        default=Path("evaluation/formal/questions.csv"),
        help="Frozen question metadata used only for deterministic adaptive routing; gold fields "
        "are never read by the retrieval or generation stages.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra"),
    )
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument(
        "--provider", choices=("openai", "anthropic", "local"), default="openai"
    )
    parser.add_argument(
        "--hybrid-profile",
        default="legacy",
        choices=sorted(HYBRID_PROFILES),
        help="Hybrid RAG ablation preset. legacy preserves the current baseline behavior.",
    )
    parser.add_argument("--max-articles", type=int, default=15)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--answer-max-tokens", type=int, default=1600,
        help="Identical maximum completion length applied to every answer arm.",
    )
    parser.add_argument("--semantic-threshold", type=float, default=0.5)
    parser.add_argument(
        "--claim-confidence-threshold",
        type=float,
        default=0.8,
        help="Minimum aligned edge confidence for Tier A claim-safe evidence.",
    )
    parser.add_argument(
        "--reuse-corpora-dir",
        type=Path,
        help="Replay from frozen <DIR>/<QID>/corpus.pubtator files without PubMed network calls.",
    )
    parser.add_argument(
        "--reuse-exposures-dir",
        type=Path,
        help="Replay frozen <DIR>/<QID>/result.json graph paths without regenerating graphs.",
    )
    parser.add_argument(
        "--reuse-graphs-dir",
        type=Path,
        help="Replay a trusted frozen <DIR>/<QID>/graph.pkl without semantic extraction calls.",
    )
    parser.add_argument(
        "--persist-graph",
        action="store_true",
        help="Persist each generated semantic graph as graph.pkl for token-free gate replay.",
    )
    parser.add_argument(
        "--graph-cache-dir",
        type=Path,
        help="Content-addressed cache for trusted semantic graphs shared across runs.",
    )
    parser.add_argument(
        "--kg-expansion-articles",
        type=int,
        default=0,
        help="Maximum second-stage PubMed documents added from KG path queries; zero disables.",
    )
    parser.add_argument(
        "--suppress-graph-answer-context",
        action="store_true",
        help="Use KG evidence only for reranking (ablation arm C), not in answer context.",
    )
    parser.add_argument(
        "--integration-policy",
        choices=("legacy", "three_stage"),
        default="legacy",
        help="three_stage falls back to Text RAG unless safe incremental paths are available.",
    )
    parser.add_argument(
        "--answer-path-policy",
        choices=("all_safe", "incremental", "local_oracle"),
        default="incremental",
        help="Which Tier-A paths may be rendered in the Hybrid answer.",
    )
    parser.add_argument(
        "--graph-answer-style",
        choices=("canonical", "natural"),
        default="canonical",
        help="Render selected paths as canonical PATH records or readable deterministic prose.",
    )
    parser.add_argument(
        "--disable-kg-reranking",
        action="store_true",
        help="Disable graph reranking so KG expansion can be tested as an isolated treatment.",
    )
    parser.add_argument(
        "--fallback-answers-dir",
        type=Path,
        help="Reuse <DIR>/<QID>/result.json Traditional answers when three-stage routing falls back.",
    )
    parser.add_argument(
        "--skip-general-llm",
        action="store_true",
        help="Generate only Hybrid and Traditional RAG answers for a token-budgeted replay.",
    )
    parser.add_argument(
        "--skip-answer-generation",
        action="store_true",
        help="Run retrieval/path replay only; makes frozen-exposure comparisons completion-token free.",
    )
    parser.add_argument(
        "--hybrid-answer-only",
        action="store_true",
        help="Generate only the Hybrid answer for low-cost PATH-compliance diagnostics.",
    )
    parser.add_argument(
        "--traditional-answer-only",
        action="store_true",
        help="Generate only the Text-RAG answer for staged semantic-equivalence screening.",
    )
    parser.add_argument(
        "--general-answer-only",
        action="store_true",
        help="Generate only the closed-book LLM answer (ablation arm A).",
    )
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=0,
        help="Stop before starting another question once provider-reported chat token usage "
        "for this process reaches this limit. Zero disables the limit.",
    )
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate selected questions even when complete checkpoints exist.",
    )
    args = parser.parse_args()

    args.run_dir.mkdir(parents=True, exist_ok=True)
    (args.run_dir / "questions").mkdir(exist_ok=True)
    lock_handle = (args.run_dir / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"Another runner is active for {args.run_dir}") from exc
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    queries = enrich_query_metadata(
        load_queries(args.queries, args.expected_question_count), args.questions_metadata
    )
    selected = [
        row for row in queries if not args.only or row["question_id"] in set(args.only)
    ]
    answer_only_flags = sum(
        bool(value)
        for value in (
            args.hybrid_answer_only,
            args.traditional_answer_only,
            args.general_answer_only,
        )
    )
    if answer_only_flags > 1:
        raise ValueError("Choose at most one answer-only system flag")
    if args.hybrid_answer_only:
        systems = ("netmedex_hybrid_rag",)
    elif args.traditional_answer_only:
        systems = ("traditional_rag",)
    elif args.general_answer_only:
        systems = ("general_llm",)
    else:
        systems = SYSTEMS[:2] if args.skip_general_llm else SYSTEMS
    run_id = f"formal-v1-{args.model}"
    if args.hybrid_profile != "legacy":
        run_id = f"{run_id}-{args.hybrid_profile}"
    manifest_path = args.run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["model"] != args.model:
            raise ValueError("Existing run uses a different model")
        if manifest.get("provider", "openai") != args.provider:
            raise ValueError("Existing run uses a different provider")
        if manifest.get("hybrid_profile", "legacy") != args.hybrid_profile:
            raise ValueError("Existing run uses a different hybrid profile")
        expected_config = {
            "integration_policy": args.integration_policy,
            "answer_path_policy": args.answer_path_policy,
            "graph_answer_style": args.graph_answer_style,
            "enable_kg_reranking": not args.disable_kg_reranking,
            "fallback_answers_dir": (
                str(args.fallback_answers_dir) if args.fallback_answers_dir else None
            ),
        }
        for field, expected in expected_config.items():
            if manifest.get(field, expected) != expected:
                raise ValueError(f"Existing run uses a different {field}")
    else:
        manifest = {
            "run_id": run_id,
            "benchmark_version": "formal-v1",
            "status": "running",
            "provider": args.provider,
            "model": args.model,
            "api": "chat_completions",
            "sampling": {
                "temperature": 1,
                "note": "GPT-5.6 supports only its default temperature in Chat Completions.",
            },
            "max_articles_per_question": args.max_articles,
            "top_k": args.top_k,
            "answer_max_tokens": args.answer_max_tokens,
            "edge_method": "semantic",
            "semantic_threshold": args.semantic_threshold,
            "claim_confidence_threshold": args.claim_confidence_threshold,
            "edge_weight_cutoff": 1,
            "hybrid_profile": args.hybrid_profile,
            "query_file": str(args.queries),
            "query_file_sha256": sha256(args.queries),
            "expected_question_count": args.expected_question_count,
            "questions_metadata_file": str(args.questions_metadata),
            "questions_metadata_sha256": sha256(args.questions_metadata),
            "gold_qrels_read_during_run": False,
            "systems": list(systems),
            "reuse_corpora_dir": str(args.reuse_corpora_dir) if args.reuse_corpora_dir else None,
            "reuse_exposures_dir": (
                str(args.reuse_exposures_dir) if args.reuse_exposures_dir else None
            ),
            "reuse_graphs_dir": str(args.reuse_graphs_dir) if args.reuse_graphs_dir else None,
            "persist_graph": args.persist_graph,
            "graph_cache_dir": str(args.graph_cache_dir) if args.graph_cache_dir else None,
            "kg_expansion_articles": args.kg_expansion_articles,
            "suppress_graph_answer_context": args.suppress_graph_answer_context,
            "integration_policy": args.integration_policy,
            "answer_path_policy": args.answer_path_policy,
            "graph_answer_style": args.graph_answer_style,
            "enable_kg_reranking": not args.disable_kg_reranking,
            "answer_generation": not args.skip_answer_generation,
            "max_total_tokens_per_process": args.max_total_tokens or None,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(manifest_path, manifest)

    attempt_started_at = datetime.now(timezone.utc).isoformat()
    attempts = manifest.setdefault("attempts", [])
    selected_question_ids = [row["question_id"] for row in selected]
    historical_question_ids = {
        question_id
        for prior_attempt in attempts
        for question_id in prior_attempt.get("selected_questions", [])
    }
    manifest["question_scope"] = sorted(
        set(manifest.get("question_scope", []))
        | historical_question_ids
        | set(selected_question_ids)
    )
    attempt = {
        "attempt_id": f"attempt-{len(attempts) + 1:03d}",
        "started_at": attempt_started_at,
        "selected_questions": selected_question_ids,
        "force": args.force,
        "status": "running",
    }
    attempts.append(attempt)
    manifest["status"] = "running"
    manifest["last_resumed_at"] = attempt_started_at
    atomic_json(manifest_path, manifest)

    llm = init_llm(args.model, args.provider)
    stopped_for_token_budget = False
    for index, row in enumerate(selected, start=1):
        process_tokens = int(
            getattr(llm, "completion_usage_totals", {}).get("total_tokens", 0) or 0
        )
        if args.max_total_tokens and process_tokens >= args.max_total_tokens:
            stopped_for_token_budget = True
            LOGGER.warning(
                "Token checkpoint reached (%s >= %s); stopping before next question",
                process_tokens,
                args.max_total_tokens,
            )
            break
        question_id = row["question_id"]
        question_dir = args.run_dir / "questions" / question_id
        question_dir.mkdir(parents=True, exist_ok=True)
        result_path = question_dir / "result.json"
        if result_path.exists() and not args.force:
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            if existing.get("status") == "complete":
                LOGGER.info("[%s/%s] %s already complete", index, len(selected), question_id)
                continue
        LOGGER.info("[%s/%s] Starting %s", index, len(selected), question_id)
        try:
            result = run_question(
                row,
                llm=llm,
                max_articles=args.max_articles,
                top_k=args.top_k,
                semantic_threshold=args.semantic_threshold,
                claim_confidence_threshold=args.claim_confidence_threshold,
                hybrid_profile=args.hybrid_profile,
                question_dir=question_dir,
                systems=systems,
                reuse_corpora_dir=args.reuse_corpora_dir,
                reuse_exposures_dir=args.reuse_exposures_dir,
                reuse_graphs_dir=args.reuse_graphs_dir,
                graph_cache_dir=args.graph_cache_dir,
                persist_graph=args.persist_graph,
                generate_answers=not args.skip_answer_generation,
                kg_expansion_articles=args.kg_expansion_articles,
                suppress_graph_answer_context=args.suppress_graph_answer_context,
                integration_policy=args.integration_policy,
                answer_path_policy=args.answer_path_policy,
                graph_answer_style=args.graph_answer_style,
                enable_kg_reranking=not args.disable_kg_reranking,
                fallback_answers_dir=args.fallback_answers_dir,
                answer_max_tokens=args.answer_max_tokens,
            )
        except Exception as exc:
            LOGGER.exception("%s failed", question_id)
            result = {
                "status": "failed",
                "question_id": question_id,
                "error": f"{type(exc).__name__}: {exc}",
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        atomic_json(result_path, result)
        complete, failed = compile_outputs(
            args.run_dir,
            queries,
            run_id,
            systems,
            require_answers=not args.skip_answer_generation,
        )
        manifest.update(
            {
                "completed_questions": complete,
                "failed_questions": failed,
                "last_checkpoint_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        atomic_json(manifest_path, manifest)

    complete, failed = compile_outputs(
        args.run_dir,
        queries,
        run_id,
        systems,
        require_answers=not args.skip_answer_generation,
    )
    if stopped_for_token_budget:
        manifest["status"] = "stopped_token_budget"
        manifest["stopped_at_tokens"] = int(
            getattr(llm, "completion_usage_totals", {}).get("total_tokens", 0) or 0
        )
        manifest["stopped_at"] = datetime.now(timezone.utc).isoformat()
    elif complete + failed == len(manifest["question_scope"]):
        manifest["status"] = "complete" if failed == 0 else "complete_with_failures"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["completed_questions"] = complete
    manifest["failed_questions"] = failed
    attempt["status"] = (
        "stopped_token_budget"
        if stopped_for_token_budget
        else ("complete" if failed == 0 else "complete_with_failures")
    )
    attempt["completed_at"] = datetime.now(timezone.utc).isoformat()
    attempt["completed_questions_after_attempt"] = complete
    attempt["failed_questions_after_attempt"] = failed
    atomic_json(manifest_path, manifest)
    LOGGER.info("Run finished: complete=%s failed=%s", complete, failed)


if __name__ == "__main__":
    main()
