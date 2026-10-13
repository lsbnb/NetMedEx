from netmedex.graph import PubTatorGraphBuilder
from netmedex.organelle_ner import find_organelle_annotations
from netmedex.pubtator_data import ANNOTATION_TYPES, PubTatorArticle


def test_cellular_component_registered_in_annotation_types():
    assert "CellularComponent" in ANNOTATION_TYPES


def test_finds_mitochondria_and_endoplasmic_reticulum():
    text = "Mitochondria and endoplasmic reticulum stress trigger apoptosis in lysosomes."
    annotations = find_organelle_annotations("1", text, None)
    matches = {a.identifier_name: a.mesh for a in annotations}

    assert matches.get("Mitochondrion") == "GO:0005739"
    assert matches.get("Endoplasmic reticulum") == "GO:0005783"
    assert matches.get("Lysosome") == "GO:0005764"
    assert all(a.type == "CellularComponent" for a in annotations)


def test_organelle_graph_builder_integration():
    article = PubTatorArticle(
        pmid="99999",
        date=None,
        journal=None,
        doi=None,
        title="Mitophagy eliminates damaged mitochondria through autophagosomes.",
        abstract="Lysosomes fuse with autophagosomes.",
        annotations=[],
        relations=[],
    )
    builder = PubTatorGraphBuilder(node_type="all")
    builder.add_article(article)
    G = builder.build()

    node_types = {d["type"] for _, d in G.nodes(data=True)}
    assert "CellularComponent" in node_types
    assert any("GO:0005739" in n for n in G.nodes)
