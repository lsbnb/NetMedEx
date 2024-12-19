from typing import Literal

import networkx as nx

from netmedex.network_core import NetworkBuilder


def filter_node(G: nx.Graph, node_degree_threshold: int):
    for node, degree in list(G.degree()):
        if degree < node_degree_threshold:
            G.remove_node(node)


def rebuild_graph(
    node_degree,
    cut_weight,
    format: Literal["xgmml", "html"],
    G=None,
    with_layout=False,
    graph_path=None,
):
    if G is None:
        G = NetworkBuilder.load_graph(graph_path)

    network_builder = NetworkBuilder(
        pubtator_filepath="",
        savepath=None,
        node_type="",
        output_filetype="",
        weighting_method="",
        edge_weight_cutoff=cut_weight,
        pmid_weight_filepath=None,
        community=G.graph.get("is_community", False),
        max_edges=G.graph.get("max_edges", 0),
        debug=False,
    )

    network_builder.remove_edges_by_weight(G)
    network_builder.remove_edges_by_rank(G)
    network_builder.remove_isolated_nodes(G)
    filter_node(G, node_degree)

    if with_layout:
        network_builder.set_network_layout(G)

    if G.graph.get("is_community", False) and format == "html":
        network_builder.set_network_communities(G)

    return G
