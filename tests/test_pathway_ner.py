import networkx as nx

from netmedex.graph_rag import GraphRetriever
from netmedex.pathway_ner import find_pathway_annotations
from netmedex.pubtator_data import ANNOTATION_TYPES
from netmedex.pubtator_graph_data import PubTatorNodeCollection


def test_finds_kegg_pathway_with_hyphen_spelling():
    annotations = find_pathway_annotations(
        "1", "Icariin activates the PI3K-Akt signaling pathway", "in osteoblasts."
    )
    matches = {a.identifier_name: a.mesh for a in annotations}
    assert matches.get("PI3K-Akt signaling pathway") == "map04151"


def test_finds_kegg_pathway_with_slash_spelling():
    # Papers inconsistently write "PI3K-Akt" (KEGG's own spelling) vs "PI3K/Akt" -- both must
    # resolve to the same canonical KEGG ID.
    annotations = find_pathway_annotations(
        "1", "Icariin activates the PI3K/Akt signaling pathway", "in osteoblasts."
    )
    matches = {a.identifier_name: a.mesh for a in annotations}
    assert matches.get("PI3K-Akt signaling pathway") == "map04151"


def test_finds_composite_pi3k_akt_mtor_literature_alias():
    annotations = find_pathway_annotations(
        "1", "PTEN inhibits PI3K/Akt/mTOR", "during osteogenic differentiation."
    )
    matches = {a.identifier_name: (a.mesh, a.type) for a in annotations}
    assert matches.get("PI3K-Akt signaling pathway") == ("map04151", "Pathway")


def test_finds_pten_pi3k_akt_hif1alpha_composite_alias():
    annotations = find_pathway_annotations(
        "1", "miRNA-21 promotes osteogenesis via the PTEN/PI3K/Akt/HIF-1alpha pathway", None
    )
    assert any(a.mesh == "map04151" and a.type == "Pathway" for a in annotations)


def test_finds_reactome_pathway():
    annotations = find_pathway_annotations(
        "1", "This study examines constitutive signaling by aberrant PI3K in cancer.", None
    )
    matches = {a.identifier_name: (a.mesh, a.type) for a in annotations}
    assert matches.get("Constitutive Signaling by Aberrant PI3K in Cancer") == ("R-HSA-2219530", "Pathway")


def test_no_match_returns_empty_list():
    annotations = find_pathway_annotations("1", "The quick brown fox.", "Nothing biomedical here.")
    assert annotations == []


def test_pathway_type_registered_in_annotation_types():
    assert "Pathway" in ANNOTATION_TYPES


def test_pathway_type_accepted_by_node_collection():
    collection = PubTatorNodeCollection(mesh_only=False, use_mesh_vocabulary=False)
    for annotation in find_pathway_annotations("1", "The Wnt signaling pathway is activated.", None):
        collection.add_node(annotation)
    node_ids = list(collection.nodes.keys())
    assert any(nid.startswith("map04310") for nid in node_ids)


def test_pathway_passes_graph_retriever_node_filter():
    graph = nx.Graph()
    graph.add_node("map04151_Pathway", name="PI3K-Akt signaling pathway", type="Pathway")
    retriever = GraphRetriever(graph)
    assert retriever._is_valid_node("map04151_Pathway")
