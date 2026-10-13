from netmedex.cell_type_ner import find_cell_type_annotations
from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


def test_finds_stem_cells_and_immune_subsets():
    text = (
        "Mesenchymal stem cells (MSCs) and tumor-associated macrophages (TAMs) "
        "modulate regulatory T cells (Tregs) and CD8+ T cells in the tumor microenvironment."
    )
    annotations = find_cell_type_annotations("1", text, None)
    names = {a.name: (a.mesh, a.identifier_name) for a in annotations}

    assert any(a.identifier_name == "Mesenchymal stem cell" for a in annotations)
    assert any(a.identifier_name == "Tumor-associated macrophage" for a in annotations)
    assert any(a.identifier_name == "Regulatory T cell" for a in annotations)
    assert any(a.identifier_name == "CD8-positive T cell" for a in annotations)
    assert all(a.type == "CellLine" for a in annotations)


def test_finds_extracellular_vesicles():
    text = "Exosomes and small extracellular vesicles (sEVs) deliver microRNAs to Kupffer cells."
    annotations = find_cell_type_annotations("1", text, None)
    assert any(a.identifier_name == "Exosome" for a in annotations)
    assert any(a.identifier_name == "Extracellular vesicle" for a in annotations)
    assert any(a.identifier_name == "Kupffer cell" for a in annotations)


def test_case_sensitive_abbreviations_avoid_common_words():
    # Lowercase "tam" or "ev" in ordinary text must NOT match
    text = "The quick brown fox did not tamper with the evidence or evaluate it."
    annotations = find_cell_type_annotations("1", text, None)
    assert annotations == []


def test_cell_type_graph_builder_integration():
    article = PubTatorArticle(
        pmid="12345",
        date=None,
        journal=None,
        doi=None,
        title="MSC-derived exosomes deliver miR-17 to Kupffer cells.",
        abstract="MSCs secrete EVs that target macrophages.",
        annotations=[],
        relations=[],
    )
    builder = PubTatorGraphBuilder(node_type="all")
    builder.add_article(article)
    G = builder.build()

    node_names = {d["name"] for _, d in G.nodes(data=True)}
    assert any("mesenchymal" in name.lower() or "msc" in name.lower() for name in node_names)
    assert any("exosome" in name.lower() for name in node_names)
    assert any("kupffer" in name.lower() for name in node_names)
