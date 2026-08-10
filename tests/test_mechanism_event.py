import networkx as nx

from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_schema import graph_schema_status
from netmedex.graph_rag import GraphRetriever
from netmedex.mechanism_event import build_mechanism_event
from netmedex.pubtator_graph_data import PubTatorEdge


def test_mechanism_event_requires_directional_quote_aligned_evidence():
    event = build_mechanism_event(
        source_id="MIR21", target_id="PTEN", pmid="34854397",
        relation="inhibits", evidence="miR-21 inhibited PTEN expression.",
        confidence=0.94, study_type="Cell-line",
    )
    assert event["source_id"] == "MIR21"
    assert event["target_id"] == "PTEN"
    assert event["grounding_status"] == "directional_quote_aligned"


def test_mechanism_event_rejects_symmetric_or_misaligned_assertion():
    assert build_mechanism_event(
        source_id="A", target_id="B", pmid="1", relation="associated_with",
        evidence="A was associated with B.", confidence=0.9,
    ) is None


def test_mechanism_event_accepts_targeting_and_negative_regulation_language():
    targeting = build_mechanism_event(
        source_id="50557_Gene", target_id="19211_Gene", pmid="35593324",
        relation="targets", evidence="miR-21 targets PTEN in osteoblasts.",
        confidence=0.9,
    )
    negative_regulation = build_mechanism_event(
        source_id="406991_Gene", target_id="19211_Gene", pmid="34854397",
        relation="downregulates",
        evidence="miR-21 promoted osteogenesis by negatively regulating PTEN.",
        confidence=0.9,
    )

    assert targeting is not None
    assert targeting["relation"] == "targets"
    assert negative_regulation is not None
    assert negative_regulation["relation"] == "downregulates"
    assert build_mechanism_event(
        source_id="A", target_id="B", pmid="1", relation="inhibits",
        evidence="A was associated with B.", confidence=0.9,
    ) is None


def test_unversioned_frozen_graph_requires_rebuild():
    status = graph_schema_status(nx.Graph())
    assert status["rebuild_required"] is True
    assert "ner_schema_version_mismatch" in status["reasons"]


def test_graph_builder_persists_mechanism_event_on_edge_and_rag_selects_it():
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    builder._add_edges([
        PubTatorEdge(
            node1_id="MIR21", node2_id="PTEN", pmid="34854397",
            relation="inhibits", confidence=0.94,
            evidence="miR-21 inhibited PTEN expression.",
            study_type="Cell-line", source_id="MIR21",
        )
    ])
    edge = builder.graph.edges["MIR21", "PTEN"]
    event = edge["mechanism_events"]["34854397"]["inhibits"]
    assert event["target_id"] == "PTEN"
    support = GraphRetriever._select_edge_support(edge)
    assert support["selected_mechanism_event"]["event_id"] == event["event_id"]
    assert graph_schema_status(builder.graph)["current"] is True


def test_existing_edge_with_null_event_container_accepts_later_grounded_event():
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    builder._add_edges([
        PubTatorEdge(
            node1_id="MIR21", node2_id="PTEN", pmid="1",
            relation="associated_with", confidence=0.8,
            evidence="MIR21 is associated with PTEN.", source_id=None,
        ),
        PubTatorEdge(
            node1_id="MIR21", node2_id="PTEN", pmid="2",
            relation="downregulates", confidence=0.9,
            evidence="MIR21 negatively regulates PTEN.", source_id="MIR21",
        ),
    ])

    events = builder.graph.edges["MIR21", "PTEN"]["mechanism_events"]
    assert events["2"]["downregulates"]["source_id"] == "MIR21"
