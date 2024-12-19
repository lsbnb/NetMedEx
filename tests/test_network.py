from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from netmedex.network_core import NetworkBuilder
from netmedex.pubtator_parser import (
    HEADER_SYMBOL,
    PubTatorEdgeData,
    PubTatorLine,
    PubTatorNodeData,
    PubTatorParser,
)


@pytest.fixture(scope="module")
def tempdir():
    with TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@pytest.fixture(scope="module")
def paths():
    return {
        "simple": "./tests/test_data/6_nodes_3_clusters_mesh.pubtator",
        "mesh_collision": "./tests/test_data/mesh_collision.pubtator",
        "merge_genes": "./tests/test_data/merge_genes.pubtator",
    }


@pytest.fixture()
def network_args():
    return {
        "pubtator_filepath": None,
        "savepath": None,
        "node_type": "all",
        "output_filetype": "html",
        "weighting_method": "freq",
        "edge_weight_cutoff": 0,
        "pmid_weight_filepath": None,
        "community": False,
        "max_edges": 0,
        "debug": False,
    }


def test_index_by_text(paths, network_args):
    network_args["pubtator_filepath"] = paths["simple"]
    network_builder = NetworkBuilder(**network_args)
    G = network_builder.run()

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "l55m should be in the graph"
    assert len(G.nodes) == 14, f"result: {len(G.nodes)} nodes\nexpected: 14 nodes"
    assert len(G.edges) == 47, f"result: {len(G.edges)} nodes\nexpected: 47 edges"


def test_index_by_relation(paths, network_args):
    network_args["pubtator_filepath"] = paths["simple"]
    network_args["node_type"] = "relation"
    network_builder = NetworkBuilder(**network_args)
    G = network_builder.run()

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "Not mapped by MeSH"
    assert len(G.nodes) == 8, f"result: {len(G.nodes)} nodes\nexpected: 8 nodes"
    assert len(G.edges) == 9, f"result: {len(G.edges)} nodes\nexpected: 9 edges"


def test_index_by_mesh(paths, network_args):
    network_args["pubtator_filepath"] = paths["simple"]
    network_args["node_type"] = "mesh"
    network_builder = NetworkBuilder(**network_args)
    G = network_builder.run()

    assert G.nodes.get(
        "RS#:854560;HGVS:p.L55M;CorrespondingGene:5444", False
    ), "Not mapped by MeSH"
    assert len(G.nodes) == 13, f"result: {len(G.nodes)} nodes\nexpected: 13 nodes"
    assert len(G.edges) == 41, f"result: {len(G.edges)} nodes\nexpected: 41 edges"


def test_mesh_collision_handling(paths, network_args):
    network_args["pubtator_filepath"] = paths["mesh_collision"]
    network_builder = NetworkBuilder(**network_args)
    G = network_builder.run()

    assert len(G.nodes) == 7, f"result: {len(G.nodes)} nodes\nexpected: 7 nodes"
    assert len(G.edges) == 21, f"result: {len(G.edges)} nodes\nexpected: 21 edges"


def test_merge_genes(paths, network_args):
    network_args["pubtator_filepath"] = paths["merge_genes"]
    network_builder = NetworkBuilder(**network_args)
    G = network_builder.run()

    assert len(G.nodes) == 7, f"result: {len(G.nodes)} nodes\nexpected: 7 nodes"
    assert len(G.edges) == 11, f"result: {len(G.nodes)} nodes\nexpected: 11 edges"


@pytest.mark.parametrize(
    "data,expected",
    [
        (f"{HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", True),
        (f"{HEADER_SYMBOL[0]}USE-MESH-VOCABULARY\nfoobar", False),
        (f"{HEADER_SYMBOL + HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", False),
    ],
)
def test_parse_header(data, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data=data))
    pubtator_line = PubTatorLine
    with mock.patch("netmedex.pubtator_parser.PubTatorLine", pubtator_line):
        parser = PubTatorParser(data, node_type="all")
        parser.parse()
        assert pubtator_line.use_mesh == expected


def test_merge_same_name_genes():
    node_dict = {
        "gene_1": PubTatorNodeData(id=1, mesh="1", type="Gene", name="foo", pmids={10}),
        "gene_2": PubTatorNodeData(id=2, mesh="2", type="Gene", name="foo", pmids={20}),
        "bar": PubTatorNodeData(id=3, mesh="-", type="Chemical", name="bar", pmids={30}),
    }
    edge_dict = {
        ("gene_1", "bar"): [PubTatorEdgeData(id=4, pmid="30"), PubTatorEdgeData(id=5, pmid="40")],
        ("gene_1", "gene_2"): [PubTatorEdgeData(id=6, pmid="20")],
        ("foo", "bar"): [PubTatorEdgeData(id=7, pmid="30"), PubTatorEdgeData(id=8, pmid="40")],
    }
    parser = PubTatorParser(pubtator_filepath="", node_type="all")
    parser.node_dict = node_dict
    parser.edge_dict = edge_dict
    parser._merge_same_name_genes()

    assert node_dict == {
        "bar": PubTatorNodeData(id=3, mesh="-", type="Chemical", name="bar", pmids={30}),
        "gene_1;2": PubTatorNodeData(id=2, mesh="1;2", type="Gene", name="foo", pmids={10, 20}),
    }
    assert edge_dict == {
        ("gene_1;2", "bar"): [
            PubTatorEdgeData(id=4, pmid="30"),
            PubTatorEdgeData(id=5, pmid="40"),
        ],
        ("foo", "bar"): [PubTatorEdgeData(id=7, pmid="30"), PubTatorEdgeData(id=8, pmid="40")],
    }


def test_save_network(tempdir, paths, network_args):
    network_args["pubtator_filepath"] = paths["simple"]
    network_args["savepath"] = str(tempdir / "output.html")
    NetworkBuilder(**network_args).run()
