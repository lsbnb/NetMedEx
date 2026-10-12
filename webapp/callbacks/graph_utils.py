from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Literal

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder, load_graph

_GRAPH_CACHE: OrderedDict[tuple, nx.Graph] = OrderedDict()
_GRAPH_CACHE_LOCK = threading.Lock()
_GRAPH_CACHE_SIZE = 2


def load_graph_cached(graph_path: str) -> nx.Graph:
    """Read-only shared copy of a session graph, keyed by path + mtime + size.

    Large prebuilt knowledge graphs (e.g. a 36k-article graph is ~200 MB and
    takes ~9 s to unpickle) are otherwise re-read on every slider change and
    every node expansion. Callers that mutate must work on ``.copy()``.
    """
    real = os.path.realpath(graph_path)
    st = os.stat(real)
    key = (real, st.st_mtime_ns, st.st_size)
    with _GRAPH_CACHE_LOCK:
        if key in _GRAPH_CACHE:
            _GRAPH_CACHE.move_to_end(key)
            return _GRAPH_CACHE[key]
    graph = load_graph(real)
    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE[key] = graph
        while len(_GRAPH_CACHE) > _GRAPH_CACHE_SIZE:
            _GRAPH_CACHE.popitem(last=False)
    return graph


def get_anchor_nodes(graph: nx.Graph) -> set:
    """Nodes exempt from the interactive-rendering safety caps.

    A graph may declare them explicitly in ``graph.graph["anchor_nodes"]`` (a
    merged multi-query knowledge graph has no single build query to match);
    otherwise they are matched against the build query as before.
    """
    declared = graph.graph.get("anchor_nodes")
    if declared:
        return {n for n in declared if n in graph}
    return PubTatorGraphBuilder.find_query_anchor_nodes(graph, graph.graph.get("query"))


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for node, degree in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


def rebuild_graph(
    node_degree: int,
    cut_weight: int | float | list[int | float],
    format: Literal["xgmml", "html"],
    graph_path: str,
    G: nx.Graph | None = None,
    with_layout: bool = False,
    community: bool = False,
    weighting_method: Literal["freq", "npmi"] = "freq",
    confidence_threshold: float = 0.0,
):
    # Scale cutoff if using NPMI (UI uses 0-1, backend uses 0-20)
    if weighting_method == "npmi":
        if isinstance(cut_weight, list):
            cut_weight = [w * 20 for w in cut_weight]
        elif isinstance(cut_weight, (int, float)):
            cut_weight = cut_weight * 20

    # Shallow copy: rebuild only reassigns attribute keys and removes
    # nodes/edges, so the cached original stays intact.
    graph = load_graph_cached(graph_path).copy() if G is None else G

    # Normalize all node names to lowercase for consistency across builds and pk versions
    for _, data in graph.nodes(data=True):
        if "name" in data and isinstance(data["name"], str):
            data["name"] = data["name"].lower()

    # Recalculate edge weights and widths based on current method
    PubTatorGraphBuilder.recalculate_edge_weights(graph, weighting_method)

    # Filter semantic edges by confidence threshold if specified
    if confidence_threshold > 0.0:
        PubTatorGraphBuilder._remove_edges_by_confidence(graph, confidence_threshold)

    # Anchor Protection: exempt nodes/edges matching the original build query
    # (e.g. a category term like "microRNA" expands to every miR-* node) from
    # the automatic safety caps below, so a low-frequency query-relevant
    # entity (e.g. miR-124 with edge weight 1) isn't silently dropped just
    # because it's globally low-ranked. Does NOT affect the user-adjustable
    # weight cutoff / node-degree filters further down.
    anchor_nodes = get_anchor_nodes(graph)

    # A large knowledge graph can open on its core entities only
    # (graph.graph["initial_view"] == "anchors"): users then grow the view by
    # connecting entities to them or expanding neighbors. Anchors are kept even
    # when no edge links them to another anchor.
    if graph.graph.get("initial_view") == "anchors" and anchor_nodes:
        graph = graph.subgraph(anchor_nodes).copy()
        graph.graph["num_communities"] = 0
        for node in graph.nodes:
            graph.nodes[node]["parent"] = None
        if with_layout:
            PubTatorGraphBuilder._set_network_layout(graph)
        PubTatorGraphBuilder.normalize_graph_ids(graph)
        return graph

    # NEW: Safety-cap for interactive rendering to prevent browser crashes
    # 1. Edge Pruning
    initial_edge_count = graph.number_of_edges()
    MAX_INTERACTIVE_EDGES = 3000
    effective_max_edges = graph.graph.get("max_edges", 0)

    # Use the smaller of user-defined max_edges or our safety cap
    if effective_max_edges <= 0 or effective_max_edges > MAX_INTERACTIVE_EDGES:
        effective_max_edges = MAX_INTERACTIVE_EDGES

    if initial_edge_count > effective_max_edges:
        print(
            f"DEBUG: Pruning large graph: {initial_edge_count} edges -> {effective_max_edges} edges limit"
        )
        PubTatorGraphBuilder._remove_edges_by_rank(
            graph, effective_max_edges, protected_nodes=anchor_nodes
        )
        graph.graph["is_pruned"] = True

    # 2. Apply cuts and rank filters (standard behavior)
    PubTatorGraphBuilder._remove_edges_by_weight(graph, edge_weight_cutoff=cut_weight)
    PubTatorGraphBuilder._remove_isolated_nodes(graph)
    filter_node(graph, node_degree)

    # 3. Node Pruning (if still too big after edge filter)
    MAX_INTERACTIVE_NODES = 1500
    if graph.number_of_nodes() > MAX_INTERACTIVE_NODES:
        # Keep nodes with highest degrees, giving anchor-protected nodes first
        # claim on the node budget (ranked among themselves by degree too).
        nodes_by_degree = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
        protected_present = [n for n, _ in nodes_by_degree if n in anchor_nodes]
        other_nodes = [n for n, _ in nodes_by_degree if n not in anchor_nodes]
        to_keep = set(protected_present[:MAX_INTERACTIVE_NODES])
        remaining_budget = MAX_INTERACTIVE_NODES - len(to_keep)
        if remaining_budget > 0:
            to_keep.update(other_nodes[:remaining_budget])
        to_remove = [n for n in graph.nodes if n not in to_keep]
        graph.remove_nodes_from(to_remove)

        # Cleanup any resulting isolated edges (shouldn't be any but let's be safe)
        PubTatorGraphBuilder._remove_isolated_nodes(graph)
        graph.graph["is_pruned"] = True

    if community and format == "html":
        PubTatorGraphBuilder._set_network_communities(graph)
    else:
        # Explicitly clear community data to avoid persistent state issues
        graph.graph["num_communities"] = 0

        # Remove community nodes and their associated edges
        to_remove_nodes = [
            n for n in graph.nodes if str(n).startswith("c") and str(n)[1:].isdigit()
        ]
        graph.remove_nodes_from(to_remove_nodes)

        # Also remove any edges that might be leftover as 'community' type
        to_remove_edges = [
            (u, v) for u, v, d in graph.edges(data=True) if d.get("type") == "community"
        ]
        graph.remove_edges_from(to_remove_edges)

        # Reset parent for remaining nodes
        for node in graph.nodes:
            graph.nodes[node]["parent"] = None

    # FINAL CLEANUP: Remove isolated nodes potentially created by community detection
    # and compute layout on the final set of visible nodes.
    PubTatorGraphBuilder._remove_isolated_nodes(graph)
    if with_layout:
        PubTatorGraphBuilder._set_network_layout(graph)

    # Enforce stable IDs based on the FINAL state of the graph
    PubTatorGraphBuilder.normalize_graph_ids(graph)

    return graph
