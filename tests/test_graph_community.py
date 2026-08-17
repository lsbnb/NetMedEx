import json
import networkx as nx
import pytest

from netmedex.community import CommunityDetector, GraphCommunity
from netmedex.graph_rag import GraphRetriever


@pytest.fixture
def sample_biomedical_graph():
    """Create a sample heterogeneous biomedical graph with clusters."""
    G = nx.Graph()

    # Cluster 1: Bone / Osteoblast module
    G.add_node("gene:RUNX2", name="RUNX2", type="gene")
    G.add_node("gene:BGLAP", name="Osteocalcin", type="gene")
    G.add_node("chemical:Icariin", name="Icariin", type="chemical")
    G.add_node("disease:Osteoporosis", name="Osteoporosis", type="disease")

    G.add_edge(
        "chemical:Icariin",
        "gene:RUNX2",
        edge_weight=3.5,
        pmids=["10000001", "10000002"],
        relations=["upregulates", "activates"],
    )
    G.add_edge(
        "gene:RUNX2",
        "gene:BGLAP",
        edge_weight=2.8,
        pmids=["10000002"],
        relations=["transcriptionally activates"],
    )
    G.add_edge(
        "chemical:Icariin",
        "disease:Osteoporosis",
        edge_weight=4.0,
        pmids=["10000003"],
        relations=["treats", "prevents"],
    )

    # Cluster 2: Kidney / Renal fibrosis module
    G.add_node("gene:TGFB1", name="TGF-beta1", type="gene")
    G.add_node("gene:SMAD3", name="SMAD3", type="gene")
    G.add_node("disease:CKD", name="Chronic Kidney Disease", type="disease")
    G.add_node("chemical:Losartan", name="Losartan", type="chemical")

    G.add_edge(
        "gene:TGFB1",
        "gene:SMAD3",
        edge_weight=3.0,
        pmids=["20000001"],
        relations=["phosphorylates"],
    )
    G.add_edge(
        "gene:SMAD3",
        "disease:CKD",
        edge_weight=3.2,
        pmids=["20000002"],
        relations=["promotes fibrosis"],
    )
    G.add_edge(
        "chemical:Losartan",
        "disease:CKD",
        edge_weight=2.5,
        pmids=["20000003"],
        relations=["attenuates"],
    )

    return G


def test_community_detector_build_and_features(sample_biomedical_graph):
    detector = CommunityDetector(sample_biomedical_graph)
    communities = detector.build_communities(min_community_size=2)

    assert len(communities) >= 2
    for comm in communities:
        assert isinstance(comm, GraphCommunity)
        assert comm.node_count >= 2
        assert comm.edge_count >= 1
        assert comm.title.startswith("Community #")
        assert len(comm.node_ids) == comm.node_count


def test_community_matching_and_scoring(sample_biomedical_graph):
    detector = CommunityDetector(sample_biomedical_graph)
    detector.build_communities()

    # Query for bone/osteoporosis
    matches = detector.match_communities(query="How does Icariin affect Osteoporosis?", top_k=1)
    assert len(matches) == 1
    top_comm, score = matches[0]
    assert score > 0
    # Should match the osteoporosis/bone cluster
    assert any("Icariin" in h or "Osteoporosis" in h for h in top_comm.top_hubs + top_comm.drug_hubs + top_comm.disease_hubs)

    # Query for kidney disease
    kidney_matches = detector.match_communities(query="TGF-beta1 regulation in Chronic Kidney Disease", top_k=1)
    assert len(kidney_matches) == 1
    top_kidney, score_k = kidney_matches[0]
    assert any("CKD" in h or "Kidney" in h or "TGF-beta1" in h for h in top_kidney.top_hubs + top_kidney.disease_hubs + top_kidney.gene_hubs)


def test_community_save_and_load(tmp_path, sample_biomedical_graph):
    detector = CommunityDetector(sample_biomedical_graph)
    detector.build_communities()

    save_path = tmp_path / "communities.json"
    detector.save_to_json(save_path)
    assert save_path.exists()

    new_detector = CommunityDetector(sample_biomedical_graph)
    loaded = new_detector.load_from_json(save_path)
    assert len(loaded) == len(detector.communities)
    assert loaded[0].title == detector.communities[0].title


def test_graph_retriever_macro_community_context(sample_biomedical_graph):
    retriever = GraphRetriever(sample_biomedical_graph)
    macro_context = retriever.get_macro_community_context(
        query="Icariin Osteoporosis osteoblast differentiation", top_k=2
    )

    assert "### Macro-Level Functional Communities:" in macro_context
    assert "Hub Entities" in macro_context
    assert "Functional Summary" in macro_context


def test_graph_retriever_subgraph_context_with_paths_includes_macro(sample_biomedical_graph):
    retriever = GraphRetriever(sample_biomedical_graph)
    nodes = ["chemical:Icariin", "disease:Osteoporosis"]
    context, paths = retriever.get_subgraph_context_with_paths(
        relevant_nodes=nodes, query="Icariin and Osteoporosis"
    )

    assert "Latent Network Mechanisms" in context
    assert "### Macro-Level Functional Communities:" in context
