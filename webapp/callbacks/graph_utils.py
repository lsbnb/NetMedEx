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
    graph = load_graph(graph_path) if G is None else G

    # Recalculate edge weights and widths based on current method
    PubTatorGraphBuilder.recalculate_edge_weights(graph, weighting_method)

    PubTatorGraphBuilder._remove_edges_by_weight(graph, edge_weight_cutoff=cut_weight)
    PubTatorGraphBuilder._remove_edges_by_rank(graph, graph.graph.get("max_edges", 0))
    PubTatorGraphBuilder._remove_isolated_nodes(graph)
    filter_node(graph, node_degree)

    if with_layout:
        PubTatorGraphBuilder._set_network_layout(graph)

    # Use the community parameter instead of graph metadata
    if community and format == "html":
        PubTatorGraphBuilder._set_network_communities(graph)

    return graph
