from unittest.mock import MagicMock

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder
from netmedex.normalization import normalize_knowledge_graph
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


def _normalizer_with_identical_embeddings():
    client = MagicMock()
    client.provider = "test"
    client.get_embeddings.side_effect = lambda names: [[1.0, 0.0] for _ in names]
    return client


def test_same_gene_name_with_distinct_species_gene_ids_is_not_merged():
    graph = nx.Graph()
    graph.add_node("406991_Gene", name="miR-21", type="Gene", mesh="406991")
    graph.add_node("387140_Gene", name="miR-21", type="Gene", mesh="387140")
    graph.add_node("100314000_Gene", name="miR-21", type="Gene", mesh="100314000")

    normalized = normalize_knowledge_graph(
        graph, _normalizer_with_identical_embeddings(), threshold=0.90
    )

    assert set(normalized) == {"406991_Gene", "387140_Gene", "100314000_Gene"}


def test_gene_aliases_merge_only_when_the_explicit_identifier_matches():
    graph = nx.Graph()
    graph.add_node("a", name="Mir21", type="Gene", mesh="406991")
    graph.add_node("b", name="microRNA-21", type="Gene", mesh="406991")

    normalized = normalize_knowledge_graph(
        graph, _normalizer_with_identical_embeddings(), threshold=0.90
    )

    assert normalized.number_of_nodes() == 1


def test_unidentified_same_name_genes_are_kept_separate():
    graph = nx.Graph()
    graph.add_node("unknown_mouse", name="PTEN", type="Gene", mesh=None)
    graph.add_node("unknown_human", name="PTEN", type="Gene", mesh=None)

    normalized = normalize_knowledge_graph(
        graph, _normalizer_with_identical_embeddings(), threshold=0.90
    )

    assert set(normalized) == {"unknown_mouse", "unknown_human"}


def test_graph_preserves_gene_id_and_records_species_as_context_only():
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    article = PubTatorArticle(
        pmid="34854397",
        date=None,
        journal=None,
        doi=None,
        title="Mir21a regulates Pten in mice",
        abstract=None,
        annotations=[
            PubTatorAnnotation("34854397", 0, 6, "Mir21a", None, "Gene", "387140"),
            PubTatorAnnotation("34854397", 26, 30, "mice", None, "Species", "10090"),
        ],
        relations=[],
    )

    builder.add_article(article, compute_edges=False)

    assert "387140_Gene" in builder.graph
    assert "MIR-FAMILY:21_miRNA" not in builder.graph
    assert builder.graph.nodes["387140_Gene"]["study_species_by_pmid"] == {
        "34854397": [{"taxon_id": "10090", "name": "mice"}]
    }


def test_acronym_expansion_and_mesh_standardization():
    from netmedex.normalization import (
        apply_node_acronym_and_mesh_standardization,
        standardize_node_name,
    )

    # 1. Test Disease acronym 'ra' and MeSH CUI D001172
    name, orig = standardize_node_name("ra", "Disease", "D001172")
    assert name == "rheumatoid arthritis"
    assert orig == "ra"

    # 2. Test Disease acronym 'oa'
    name, orig = standardize_node_name("oa", "Disease", "D010003")
    assert name == "osteoarthritis"
    assert orig == "oa"

    # 3. Test Chemical acronym 'ra' (retinoic acid vs rheumatoid arthritis based on node_type)
    name, orig = standardize_node_name("ra", "Chemical", None)
    assert name == "retinoic acid"
    assert orig == "ra"

    # 4. Protection test ("張冠李戴" Guard): Gene node named 'RA' must NEVER be expanded!
    name, orig = standardize_node_name("RA", "Gene", "5914")
    assert name == "RA"
    assert orig is None

    # 5. Full graph test
    g = nx.Graph()
    g.add_node("n1", name="ra", type="Disease", mesh="D001172")
    g.add_node("n2", name="oa", type="Disease", mesh="D010003")
    g.add_node("n3", name="sle", type="Disease", mesh="D008180")
    g.add_node("n4", name="RA", type="Gene", mesh="5914")

    count = apply_node_acronym_and_mesh_standardization(g)
    assert count == 3

    assert g.nodes["n1"]["name"] == "rheumatoid arthritis"
    assert "ra" in g.nodes["n1"]["aliases"]

    assert g.nodes["n2"]["name"] == "osteoarthritis"
    assert "oa" in g.nodes["n2"]["aliases"]

    assert g.nodes["n3"]["name"] == "systemic lupus erythematosus"
    assert "sle" in g.nodes["n3"]["aliases"]

    # Gene node untouched
    assert g.nodes["n4"]["name"] == "RA"
