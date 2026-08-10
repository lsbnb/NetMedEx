import networkx as nx

from netmedex.graph_rag import GraphRetriever
from netmedex.phenotype_ner import find_phenotype_annotations
from netmedex.pubtator_data import ANNOTATION_TYPES
from netmedex.pubtator_graph_data import PubTatorNodeCollection


def test_finds_go_biological_process_term():
    annotations = find_phenotype_annotations(
        "1", "Icariin promotes osteoblast differentiation", "via the PI3K/AKT pathway."
    )
    matches = {a.identifier_name: a.mesh for a in annotations}
    assert matches.get("osteoblast differentiation") == "GO:0001649"


def test_finds_hpo_phenotype_term():
    annotations = find_phenotype_annotations(
        "1", "A patient presented with torticollis and lymphadenopathy.", None
    )
    matches = {a.identifier_name: (a.mesh, a.type) for a in annotations}
    assert matches.get("Torticollis") == ("HP:0000473", "Phenotype")
    assert matches.get("Lymphadenopathy") == ("HP:0002716", "Phenotype")


def test_longest_match_wins_and_is_non_overlapping():
    # "myoblast proliferation" is itself a GO term (GO:0051450), distinct from a hypothetical
    # shorter match on "proliferation" alone -- the longer, more specific span must win, and it
    # must not also emit a second overlapping match for a sub-span.
    annotations = find_phenotype_annotations("1", "Assay of myoblast proliferation in vitro.", None)
    spans = [(a.start, a.end, a.identifier_name) for a in annotations]
    assert any(name == "myoblast proliferation" for _, _, name in spans)
    myoblast_span = next((s, e) for s, e, name in spans if name == "myoblast proliferation")
    assert not any(
        (s, e) != myoblast_span and not (e <= myoblast_span[0] or s >= myoblast_span[1])
        for s, e, _ in spans
    )


def test_no_match_returns_empty_list():
    annotations = find_phenotype_annotations("1", "The quick brown fox.", "Nothing biomedical here.")
    assert annotations == []


def test_new_types_registered_in_annotation_types():
    assert "BiologicalProcess" in ANNOTATION_TYPES
    assert "Phenotype" in ANNOTATION_TYPES


def test_new_types_accepted_by_node_collection():
    collection = PubTatorNodeCollection(mesh_only=False, use_mesh_vocabulary=False)
    for annotation in find_phenotype_annotations(
        "1", "Icariin promotes osteoblast differentiation.", None
    ):
        collection.add_node(annotation)
    node_ids = list(collection.nodes.keys())
    assert any(nid.startswith("GO:0001649") for nid in node_ids)


def test_biologicalprocess_and_phenotype_pass_graph_retriever_node_filter():
    graph = nx.Graph()
    graph.add_node("GO:0001649_BiologicalProcess", name="osteoblast differentiation", type="BiologicalProcess")
    graph.add_node("HP:0000473_Phenotype", name="Torticollis", type="Phenotype")
    retriever = GraphRetriever(graph)
    assert retriever._is_valid_node("GO:0001649_BiologicalProcess")
    assert retriever._is_valid_node("HP:0000473_Phenotype")
