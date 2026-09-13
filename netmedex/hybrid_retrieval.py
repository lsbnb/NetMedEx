"""Deterministic routing, graph caching, and KG-driven PubMed expansion helpers."""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

from netmedex.graph import safe_load_graph_pickle


GRAPH_QUESTION_TYPES = {
    "mechanism",
    "hypothesis",
    "two_hop_path",
    "multilingual_mechanism",
    "discovery",
}

GENERIC_BRIDGES = {
    "activity",
    "cancer",
    "cell",
    "cells",
    "disease",
    "effect",
    "expression",
    "inflammation",
    "mechanism",
    "pathway",
    "patients",
    "protein",
    "signaling",
    "tumor",
}


@dataclass(frozen=True)
class RouteDecision:
    use_graph: bool
    mode: str
    reason: str


def route_query(question_type: str, question: str) -> RouteDecision:
    """Route only mechanism/multi-hop/discovery questions through the KG."""
    normalized = (question_type or "").strip().casefold()
    if normalized in GRAPH_QUESTION_TYPES:
        return RouteDecision(True, "kg_multi_hop", f"question_type={normalized}")
    if normalized:
        return RouteDecision(False, "text_only", f"question_type={normalized}")
    lowered = (question or "").casefold()
    cues = (
        "2-hop",
        "two-hop",
        "multi-hop",
        "mechanism",
        "mediate",
        "mediator",
        "pathway linking",
        "testable hypothesis",
        "discover",
        "hidden link",
    )
    if any(cue in lowered for cue in cues):
        return RouteDecision(True, "kg_multi_hop", "mechanism/multi-hop keyword")
    return RouteDecision(False, "text_only", "no graph-specific intent")


def _normal(value: object) -> str:
    return " ".join(re.sub(r"[^\w-]+", " ", str(value).casefold()).split())


def is_generic_bridge(value: object) -> bool:
    normalized = _normal(value)
    return not normalized or normalized in GENERIC_BRIDGES or len(normalized) < 3


def filter_expansion_paths(paths: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep retrieval-safe, cross-document paths with at least one specific bridge.

    This gate is for query expansion, not claim generation. Tier-B paths may expand
    retrieval, but only downstream claim-safe paths may be stated as evidence.
    """
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        if not path.get("retrieval_safe", True):
            continue
        if float(path.get("query_endpoint_coverage", 1.0) or 0) < 1.0:
            continue
        if float(path.get("requested_bridge_coverage", 1.0) or 0) < 1.0:
            continue
        names = [str(name) for name in path.get("names", [])]
        if len(names) < 3 or all(is_generic_bridge(name) for name in names[1:-1]):
            continue
        groups = [set(map(str, group)) for group in path.get("edge_pmids", []) if group]
        if len(groups) < 2 or len(set().union(*groups)) < 2:
            continue
        signature = tuple(_normal(name) for name in names)
        if signature in seen:
            continue
        seen.add(signature)
        accepted.append(path)
    return accepted


def build_pubmed_expansion_queries(
    paths: Iterable[dict[str, Any]], *, max_queries: int = 6
) -> list[str]:
    """Create bounded endpoint/bridge PubMed queries from auditable KG paths."""
    queries: list[str] = []
    seen: set[str] = set()
    for path in filter_expansion_paths(paths):
        names = [str(name).strip() for name in path.get("names", [])]
        endpoint_pairs = [(names[0], names[-1])]
        endpoint_pairs.extend((names[0], bridge) for bridge in names[1:-1])
        endpoint_pairs.extend((bridge, names[-1]) for bridge in names[1:-1])
        for left, right in endpoint_pairs:
            if is_generic_bridge(left) or is_generic_bridge(right):
                continue
            query = f'"{left}"[Title/Abstract] AND "{right}"[Title/Abstract]'
            key = query.casefold()
            if key not in seen:
                seen.add(key)
                queries.append(query)
            if len(queries) >= max_queries:
                return queries
    return queries


def merge_expanded_ranking(
    original: list[tuple[str, float]],
    expanded: list[tuple[str, float]],
    added_pmids: Iterable[str],
    *,
    top_k: int,
    expansion_slots: int = 2,
    min_margin: float = 0.03,
) -> tuple[list[tuple[str, float]], dict[str, Any]]:
    """Bound expansion so novel documents cannot flush the first-stage ranking.

    Up to ``expansion_slots`` newly retrieved records may replace tail records, and
    only when their semantic score beats the original tail by ``min_margin``.
    """
    original_top = list(original[:top_k])
    if not original_top or expansion_slots <= 0:
        return original_top, {"accepted_added_pmids": [], "expansion_slots": 0}
    added = set(map(str, added_pmids))
    expanded_by_pmid = {str(pmid): float(score) for pmid, score in expanded}
    candidates = sorted(
        (
            (pmid, score)
            for pmid, score in expanded_by_pmid.items()
            if pmid in added
        ),
        key=lambda item: (-item[1], item[0]),
    )
    slots = min(expansion_slots, top_k, len(candidates))
    protected_count = max(0, top_k - slots)
    protected = original_top[:protected_count]
    tail = original_top[protected_count:]
    threshold = min((score for _pmid, score in tail), default=original_top[-1][1])
    accepted = [item for item in candidates if item[1] >= threshold + min_margin][:slots]
    remaining_slots = top_k - len(protected) - len(accepted)
    merged = protected + accepted + tail[: max(0, remaining_slots)]
    merged.sort(key=lambda item: (-item[1], item[0]))
    return merged[:top_k], {
        "method": "bounded_expansion_slots_v1",
        "expansion_slots": slots,
        "min_margin": min_margin,
        "original_tail_threshold": threshold,
        "accepted_added_pmids": [pmid for pmid, _score in accepted],
    }


class PersistentGraphCache:
    """Content-addressed cache for trusted, locally generated NetworkX graphs."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(corpus_bytes: bytes, config: dict[str, Any]) -> str:
        digest = hashlib.sha256()
        digest.update(corpus_bytes)
        digest.update(json.dumps(config, sort_keys=True).encode("utf-8"))
        return digest.hexdigest()

    def load(self, key: str) -> nx.Graph | None:
        graph_path = self.root / f"{key}.pkl"
        manifest_path = self.root / f"{key}.json"
        if not graph_path.exists() or not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("key") != key:
            return None
        # Restricted unpickler: this is our own sha256-named cache, but a raw pickle.load
        # would still execute arbitrary code for anyone who can write into the cache dir.
        graph = safe_load_graph_pickle(graph_path.read_bytes())
        if not isinstance(graph, nx.Graph):
            raise TypeError(f"Cached object is not a NetworkX graph: {type(graph)!r}")
        return graph

    def store(self, key: str, graph: nx.Graph, config: dict[str, Any]) -> None:
        graph_path = self.root / f"{key}.pkl"
        manifest_path = self.root / f"{key}.json"
        graph_tmp = graph_path.with_suffix(".pkl.tmp")
        manifest_tmp = manifest_path.with_suffix(".json.tmp")
        with graph_tmp.open("wb") as handle:
            pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
        manifest_tmp.write_text(
            json.dumps(
                {
                    "key": key,
                    "config": config,
                    "node_count": graph.number_of_nodes(),
                    "edge_count": graph.number_of_edges(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        graph_tmp.replace(graph_path)
        manifest_tmp.replace(manifest_path)
