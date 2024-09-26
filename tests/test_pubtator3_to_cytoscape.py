import networkx as nx
import pytest

from pubtoscape.pubtator3_to_cytoscape_cli import (add_edge_to_graph,
                                                   add_node_to_graph,
                                                   parse_pubtator,
                                                   remove_isolated_nodes)


@pytest.fixture(scope="module")
def filepath():
    return ["./tests/test_data/6_nodes_3_clusters_mesh.pubtator"]


def build_graph(result):
    G = nx.Graph()
    add_node_to_graph(G, result["node_dict"], result["non_isolated_nodes"])
    add_edge_to_graph(G, result["node_dict"], result["edge_dict"], None, "freq")
    remove_isolated_nodes(G)

    return G


def test_index_by_text(filepath):
    result = parse_pubtator(filepath[0], node_type="all")
    G = build_graph(result)

    assert G.nodes.get("l55m", False), "l55m should be in the graph"
    assert len(G.nodes) == 14, f"result: {len(G.nodes)} nodes\nexpected: 14 nodes"
    assert len(G.edges) == 47, f"result: {len(G.edges)} nodes\nexpected: 47 edges"


def test_index_by_relation(filepath):
    result = parse_pubtator(filepath[0], node_type="relation")
    G = build_graph(result)

    assert G.nodes.get("l55m", False), "Not mapped by MeSH"
    assert len(G.nodes) == 8, f"result: {len(G.nodes)} nodes\nexpected: 8 nodes"
    assert len(G.edges) == 9, f"result: {len(G.edges)} nodes\nexpected: 9 edges"


def test_index_by_mesh(filepath):
    result = parse_pubtator(filepath[0], node_type="mesh")
    G = build_graph(result)

    assert G.nodes.get("l55m", False), "Not mapped by MeSH"
    assert len(G.nodes) == 13, f"result: {len(G.nodes)} nodes\nexpected: 13 nodes"
    assert len(G.edges) == 41, f"result: {len(G.edges)} nodes\nexpected: 41 edges"
