from typing import Literal

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder, load_graph


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for node, degree in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


def rebuild_graph(
    node_degree: int,
    cut_weight: int | float,
    format: Literal["xgmml", "html"],
    graph_path: str,
    G: nx.Graph | None = None,
    with_layout: bool = False,
):
    graph = load_graph(graph_path) if G is None else G

    PubTatorGraphBuilder._remove_edges_by_weight(graph, edge_weight_cutoff=cut_weight)
    PubTatorGraphBuilder._remove_edges_by_rank(graph, graph.graph.get("max_edges", 0))
    PubTatorGraphBuilder._remove_isolated_nodes(graph)
    filter_node(graph, node_degree)

    if with_layout:
        PubTatorGraphBuilder._set_network_layout(graph)

    if graph.graph.get("is_community", False) and format == "html":
        PubTatorGraphBuilder._set_network_communities(graph)

    return graph
