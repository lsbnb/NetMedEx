from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import pytest

from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_parser import PubTatorIO


def _load_collection(path: Path):
    return PubTatorIO.parse(path)


def _build_graph(
    pubtator_file: Path,
    node_type: Literal["all", "mesh", "relation"] = "all",
    weighting_method: Literal["npmi", "freq"] = "freq",
    edge_weight_cutoff: int = 0,
    community: bool = False,
    max_edges: int = 0,
):
    collection = _load_collection(pubtator_file)
    builder = PubTatorGraphBuilder(node_type=node_type)
    builder.add_collection(collection)
    return builder.build(
        weighting_method=weighting_method,
        edge_weight_cutoff=edge_weight_cutoff,
        community=community,
        max_edges=max_edges,
    )


@pytest.fixture(scope="module")
def paths(data_dir: Path):
    return {
        "simple": data_dir / "6_nodes_3_clusters_mesh.pubtator",
        "mesh_collision": data_dir / "mesh_collision.pubtator",
        # "merge_genes": data_dir / "merge_genes.pubtator",  # Genes with the same name are not merged anymore
        "variant_matching": data_dir / "variant_relation_extraction.pubtator",
    }


@pytest.fixture(scope="module")
def tempdir():
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


def test_index_by_text(paths):
    G = _build_graph(paths["simple"], node_type="all")

    variant_id = "tmVar:p|SUB|L|55|M;HGVS:p.L55M;VariantGroup:1;CorrespondingGene:5444;RS#:854560;CorrespondingSpecies:9606;CA#:123413_ProteinMutation"
    assert variant_id in G.nodes, "Variant L55M should be present"
    assert len(G.nodes) == 14
    assert len(G.edges) == 47


def test_index_by_relation(paths):
    G = _build_graph(paths["simple"], node_type="relation")

    variant_id = "tmVar:p|SUB|L|55|M;HGVS:p.L55M;VariantGroup:1;CorrespondingGene:5444;RS#:854560;CorrespondingSpecies:9606;CA#:123413_ProteinMutation"
    assert variant_id in G.nodes, "Variant is excluded in 'relation' mode"
    assert len(G.nodes) == 8
    assert len(G.edges) == 9


def test_index_by_mesh(paths):
    G = _build_graph(paths["simple"], node_type="mesh")

    variant_id = "tmVar:p|SUB|L|55|M;HGVS:p.L55M;VariantGroup:1;CorrespondingGene:5444;RS#:854560;CorrespondingSpecies:9606;CA#:123413_ProteinMutation"
    assert variant_id in G.nodes, "Variant is excluded in 'mesh' mode"
    assert len(G.nodes) == 13
    assert len(G.edges) == 41


def test_mesh_collision(paths):
    G = _build_graph(paths["mesh_collision"])
    assert len(G.nodes) == 7
    assert len(G.edges) == 21


# def test_merge_genes(paths):
#     G = _build_graph(paths["merge_genes"])
#     assert len(G.nodes) == 7
#     assert len(G.edges) == 11


def test_variant_matching(paths):
    G = _build_graph(paths["variant_matching"], node_type="relation")
    assert len(G.nodes) == 22
    assert len(G.edges) == 24


def test_edge_pmid_list(paths):
    G = _build_graph(paths["simple"])

    rels = G.edges["5444_Gene", "MESH:D000086382_Disease"]["relations"]
    pmid_set = set(rels.keys())
    expected = {"34205807", "34895069", "35883435"}

    assert pmid_set == expected
