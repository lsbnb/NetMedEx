from __future__ import annotations

from typing import Literal

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder, load_graph


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
):
    # Scale cutoff if using NPMI (UI uses 0-1, backend uses 0-20)
    if weighting_method == "npmi":
        if isinstance(cut_weight, list):
            cut_weight = [w * 20 for w in cut_weight]
        elif isinstance(cut_weight, (int, float)):
            cut_weight = cut_weight * 20

    graph = load_graph(graph_path) if G is None else G

    # Recalculate edge weights and widths based on current method
    PubTatorGraphBuilder.recalculate_edge_weights(graph, weighting_method)

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
        PubTatorGraphBuilder._remove_edges_by_rank(graph, effective_max_edges)
        graph.graph["is_pruned"] = True

    # 2. Apply cuts and rank filters (standard behavior)
    PubTatorGraphBuilder._remove_edges_by_weight(graph, edge_weight_cutoff=cut_weight)
    PubTatorGraphBuilder._remove_isolated_nodes(graph)
    filter_node(graph, node_degree)

    # 3. Node Pruning (if still too big after edge filter)
    MAX_INTERACTIVE_NODES = 1500
    if graph.number_of_nodes() > MAX_INTERACTIVE_NODES:
        # Keep nodes with highest degrees
        nodes_by_degree = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
        to_keep = {n[0] for n in nodes_by_degree[:MAX_INTERACTIVE_NODES]}
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
