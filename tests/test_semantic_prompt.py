from __future__ import annotations

from types import SimpleNamespace

import networkx as nx

from netmedex.claim_verifier import (
    relation_supported_by_text,
    verify_answer_graph_claims,
    verify_claim_to_path,
)
from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.pubtator_graph_data import PubTatorNode
from netmedex.pubtator_parser import PubTatorIO
from netmedex.semantic_re import SemanticRelationshipExtractor


def _sample_entities():
    return [
        {"id": "MESH:D012559_Disease", "name": "Retinal Diseases", "type": "Disease", "mesh": "D012559"},
        {"id": "MESH:D007333_Chemical", "name": "Lutein", "type": "Chemical", "mesh": "D007333"},
    ]


def _graph_retriever_with_supported_edge():
    graph = nx.Graph()
    graph.add_node("drug", name="Drug", type="chemical")
    graph.add_node("gene", name="Gene", type="gene")
    graph.add_edge(
        "drug",
        "gene",
        edge_weight=1.0,
        relations={"20": {"associated_with"}, "10": {"inhibits"}},
        evidences={
            "20": {"associated_with": "Drug and Gene were observed together."},
            "10": {"inhibits": "Drug inhibited Gene activity."},
        },
        confidences={
            "20": {"associated_with": 0.99},
            "10": {"inhibits": 0.85},
        },
    )
    return GraphRetriever(graph)


def test_graph_rag_selects_aligned_canonical_edge_support():
    retriever = _graph_retriever_with_supported_edge()

    support = retriever._select_edge_support(retriever.graph.edges["drug", "gene"])

    assert support == {
        "selected_relation": "inhibits",
        "selected_pmid": "10",
        "selected_quote": "Drug inhibited Gene activity.",
            "selected_confidence": 0.85,
            "directional": True,
            "quote_relation_aligned": True,
            "support_tier": "A",
        "support_reasons": [
            "quote_present",
            "confidence_present",
            "confidence_ge_0.8",
                "directional_relation",
                "quote_relation_aligned",
        ],
    }


def test_graph_rag_marks_incomplete_support_as_tier_b():
    support = GraphRetriever._select_edge_support(
        {
            "relations": {"123": {"activates"}},
            "evidences": {"123": {"activates": "A activated B."}},
        }
    )

    assert support["selected_relation"] == "activates"
    assert support["selected_quote"] == "A activated B."
    assert support["selected_confidence"] is None
    assert support["support_tier"] == "B"
    assert "confidence_missing" in support["support_reasons"]


def test_graph_rag_keeps_aligned_low_confidence_quote_as_tier_b():
    support = GraphRetriever._select_edge_support(
        {
            "relations": {"123": {"activates"}},
            "evidences": {"123": {"activates": "A activated B."}},
            "confidences": {"123": {"activates": 0.79}},
        }
    )

    assert support["selected_quote"] == "A activated B."
    assert support["support_tier"] == "B"
    assert "confidence_below_0.8" in support["support_reasons"]


def test_graph_rag_claim_threshold_is_configurable_to_0_7():
    edge = {
        "relations": {"123": {"activates"}},
        "evidences": {"123": {"activates": "A activated B."}},
        "confidences": {"123": {"activates": 0.75}},
    }

    assert GraphRetriever._select_edge_support(edge)["support_tier"] == "B"
    assert GraphRetriever._select_edge_support(edge, 0.7)["support_tier"] == "A"


def test_graph_rag_structured_path_fields_share_canonical_support():
    retriever = _graph_retriever_with_supported_edge()

    context, paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="How does Drug inhibit Gene?", max_hops=1
    )

    assert len(paths) == 1
    path = paths[0]
    support = path["edge_supports"][0]
    assert path["relations"] == [support["selected_relation"]]
    assert path["edge_pmids"] == [[support["selected_pmid"]]]
    assert path["edge_evidence_quotes"] == [[support["selected_quote"]]]
    assert path["edge_evidence_complete"] == [True]
    assert "PMID:10; relation=inhibits; confidence=0.850" in context


def test_graph_rag_canonical_selection_is_deterministic():
    edge_data = {
        "relations": {"2": {"activates"}, "1": {"inhibits"}},
        "evidences": {
            "2": {"activates": "A activates B."},
            "1": {"inhibits": "A inhibits B."},
        },
        "confidences": {"2": {"activates": 0.9}, "1": {"inhibits": 0.9}},
    }

    selections = [GraphRetriever._select_edge_support(edge_data) for _ in range(5)]

    assert {item["selected_pmid"] for item in selections} == {"1"}
    assert {item["selected_relation"] for item in selections} == {"inhibits"}


def test_graph_rag_canonical_selection_normalizes_numeric_pmids():
    support = GraphRetriever._select_edge_support(
        {
            "relations": {123: {"inhibits"}},
            "evidences": {123: {"inhibits": "A inhibits B."}},
            "confidences": {123: {"inhibits": "0.81"}},
        }
    )

    assert support["selected_pmid"] == "123"
    assert support["selected_quote"] == "A inhibits B."
    assert support["selected_confidence"] == 0.81
    assert support["support_tier"] == "A"


def test_graph_rag_anchor_bonus_reranks_close_path_toward_query_target():
    graph = nx.Graph()
    for node_id in ("source", "target", "other"):
        graph.add_node(node_id, name=node_id.title(), type="gene")
    common = {
        "relations": {"1": {"associated_with"}},
        "evidences": {"1": {"associated_with": "Supported association."}},
        "confidences": {"1": {"associated_with": 0.9}},
    }
    # The irrelevant path has a slightly stronger base edge score. Anchor
    # reranking should overcome only this small margin.
    graph.add_edge("source", "target", edge_weight=0.9, **common)
    graph.add_edge("source", "other", edge_weight=1.0, **common)

    _, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"], query="How does Source affect Target?", max_hops=1
    )
    by_end = {path["node_ids"][-1]: path for path in paths}

    assert by_end["other"]["base_score"] > by_end["target"]["base_score"]
    assert by_end["target"]["score"] > by_end["other"]["score"]
    assert by_end["target"]["anchor_bonus"] == 0.08
    assert by_end["target"]["anchor_features"]["end_matches_query_focus"] is True
    assert by_end["target"]["anchor_features"]["path_spans_multiple_anchor_types"] is True


def test_graph_rag_anchor_features_recognize_explicit_mechanism_bridge():
    graph = nx.Graph()
    for node_id in ("source", "bridge", "noise", "target"):
        graph.add_node(node_id, name=node_id.title(), type="gene")

    def add_supported_edge(left, right, relation):
        quote = f"{left} {relation} {right}."
        graph.add_edge(
            left,
            right,
            edge_weight=1.0,
            relations={"1": {relation}},
            evidences={"1": {relation: quote}},
            confidences={"1": {relation: 0.9}},
        )

    add_supported_edge("source", "bridge", "activates")
    add_supported_edge("bridge", "target", "inhibits")
    add_supported_edge("source", "noise", "associated_with")
    add_supported_edge("noise", "target", "associated_with")

    _, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"], query="How does Source affect Target via Bridge?", max_hops=2
    )
    bridge_path = next(
        path for path in paths if path["node_ids"] == ["source", "bridge", "target"]
    )
    noise_path = next(path for path in paths if path["node_ids"] == ["source", "noise", "target"])

    assert bridge_path["anchor_bonus"] == 0.12
    assert noise_path["anchor_bonus"] == 0.08
    assert bridge_path["anchor_features"]["mechanism_anchor_ids"] == ["bridge"]
    assert bridge_path["anchor_features"]["bridge_matches_mechanism_context"] is True
    assert bridge_path["score"] > noise_path["score"]


def test_graph_rag_anchor_bonus_is_bounded_and_single_source_does_not_inflate_score():
    retriever = _graph_retriever_with_supported_edge()

    _, single_anchor_paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="Drug", max_hops=1
    )
    _, two_anchor_paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="How does Drug inhibit Gene?", max_hops=1
    )

    assert single_anchor_paths[0]["anchor_bonus"] == 0.0
    assert two_anchor_paths[0]["anchor_bonus"] <= 0.12


def test_graph_rag_anchor_normalization_matches_gene_suffix_and_plural_disease():
    graph = nx.Graph()
    graph.add_node("il17a", name="IL17A", type="gene")
    graph.add_node("autoimmune", name="Autoimmune Diseases", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "How is IL-17 associated with autoimmune disease?", {}
    )

    assert anchors["source_ids"] == {"il17a"}
    assert anchors["target_ids"] == {"autoimmune"}


def test_graph_rag_anchor_groups_duplicate_source_alias_ids():
    graph = nx.Graph()
    graph.add_node("human_cftr", name="CFTR", type="gene")
    graph.add_node("mouse_cftr", name="CFTR", type="gene")
    graph.add_node("inflammation", name="intestinal inflammation", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "What mechanisms connect CFTR variants to intestinal inflammation?", {}
    )
    _, features = retriever._score_path_anchors(
        ["mouse_cftr", "inflammation"], anchors
    )

    assert anchors["source_ids"] == {"human_cftr", "mouse_cftr"}
    assert anchors["target_ids"] == {"inflammation"}
    assert features["start_matches_query_focus"] is True
    assert features["end_matches_query_focus"] is True


def test_graph_rag_anchor_groups_duplicate_target_alias_ids():
    graph = nx.Graph()
    graph.add_node("metformin", name="metformin", type="chemical")
    graph.add_node("ampk", name="AMPK", type="gene")
    graph.add_node("mtor_a", name="mTOR", type="gene")
    graph.add_node("mtor_b", name="mTOR", type="gene")
    graph.add_node("cancer", name="cancer", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "How does metformin cause AMPK-mediated inhibition of mTOR signaling in cancer cells?",
        {},
    )

    assert anchors["source_ids"] == {"metformin"}
    assert anchors["mechanism_ids"] == {"ampk"}
    assert anchors["target_ids"] == {"mtor_a", "mtor_b"}
    assert anchors["contextual_ids"] == {"cancer"}


def test_graph_rag_anchor_matches_non_display_aliases_for_both_endpoints():
    graph = nx.Graph()
    graph.add_node(
        "chb",
        name="CHB",
        aliases={"CHB", "chronic hepatitis B", "chronic hepatitis B infection"},
        type="disease",
    )
    graph.add_node(
        "hcc",
        name="HCC",
        aliases={"HCC", "hepatocellular carcinoma"},
        type="disease",
    )
    graph.add_node("generic_infection", name="infection", type="disease")
    graph.add_node("generic_carcinoma", name="carcinoma", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "What mechanisms connect chronic hepatitis B infection to hepatocellular carcinoma?",
        {},
    )

    assert anchors["source_ids"] == {"chb"}
    assert anchors["target_ids"] == {"hcc"}


def test_graph_rag_uses_semantic_target_only_when_exact_target_is_missing():
    graph = nx.Graph()
    graph.add_node("smn", name="SMN", type="gene")
    graph.add_node("mito", name="mitochondrial diseases", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "Which intermediates connect SMN deficiency to mitochondrial dysfunction?",
        {"mito": 0.7},
        semantic_source_ids={"smn"},
        semantic_target_ids={"mito"},
    )

    assert anchors["source_ids"] == {"smn"}
    assert anchors["target_ids"] == {"mito"}
    assert anchors["semantic_endpoint_fallback"] is True


def test_graph_rag_does_not_reverse_exact_target_into_source_role():
    graph = nx.Graph()
    graph.add_node("dystrophin", name="dystrophin", type="gene")
    graph.add_node("inflammation", name="chronic inflammation", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "Which intermediates connect dystrophin deficiency to chronic inflammation?",
        {"dystrophin": 0.7},
        semantic_source_ids={"dystrophin"},
        semantic_target_ids={"inflammation"},
    )

    assert anchors["source_ids"] == {"dystrophin"}
    assert anchors["target_ids"] == {"inflammation"}


def test_graph_rag_explicit_roles_do_not_promote_source_fragment_to_target():
    graph = nx.Graph()
    graph.add_node("hbv", name="hepatitis b", type="disease")
    graph.add_node("infection", name="infections", type="disease")
    graph.add_node("hcc", name="carcinoma hepatocellular", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "Which intermediates connect chronic hepatitis B infection to "
        "hepatocellular carcinoma?",
        {"hcc": 0.8},
        semantic_source_ids={"hbv"},
        semantic_target_ids={"hcc"},
    )

    assert anchors["source_ids"] == {"hbv"}
    assert anchors["target_ids"] == {"hcc"}
    assert "infection" not in anchors["target_ids"]


def test_graph_rag_endpoint_phrase_accepts_ontology_word_order_variant():
    graph = nx.Graph()
    graph.add_node("hbv", name="hepatitis b", type="disease")
    graph.add_node("chb", name="hepatitis b chronic", type="disease")
    graph.add_node("infection", name="infections", type="disease")
    graph.add_node("hcc", name="carcinoma hepatocellular", type="disease")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "Which intermediates connect chronic hepatitis B infection to "
        "hepatocellular carcinoma?",
        {},
    )

    assert anchors["source_ids"] == {"hbv", "chb"}
    assert anchors["target_ids"] == {"hcc"}
    assert "infection" not in anchors["source_ids"]


def test_graph_rag_extracts_bridge_question_endpoint_phrases():
    assert GraphRetriever._extract_endpoint_phrases(
        "Which intermediates connect SMN deficiency to mitochondrial dysfunction?"
    ) == ("smn deficiency", "mitochondrial dysfunction")


def test_graph_rag_semantic_endpoint_guard_rejects_sibling_outcome():
    graph = nx.Graph()
    graph.add_node("apoptosis", name="apoptosis", type="disease")
    graph.add_node("pyroptosis", name="pyroptosis", type="disease")

    assert GraphRetriever._endpoint_lexically_compatible(
        "apoptosis", "apoptosis", graph.nodes["apoptosis"]
    )
    assert not GraphRetriever._endpoint_lexically_compatible(
        "apoptosis", "pyroptosis", graph.nodes["pyroptosis"]
    )


def test_graph_rag_semantic_endpoint_guard_accepts_acronym_and_ontology_variant():
    graph = nx.Graph()
    graph.add_node("irae", name="irAE", type="disease")
    graph.add_node("mito", name="mitochondrial diseases", type="disease")

    assert GraphRetriever._endpoint_lexically_compatible(
        "immune-related adverse events", "irae", graph.nodes["irae"]
    )
    assert GraphRetriever._endpoint_lexically_compatible(
        "mitochondrial dysfunction", "mito", graph.nodes["mito"]
    )


def test_graph_rag_explicit_bridge_query_requires_both_resolved_endpoints():
    graph = nx.Graph()
    graph.add_node("curcumin", name="curcumin", type="chemical")
    graph.add_node("pyroptosis", name="pyroptosis", type="disease")
    graph.add_edge("curcumin", "pyroptosis")
    retriever = GraphRetriever(graph)
    anchors = retriever._extract_query_anchors(
        "Which intermediates connect curcumin to apoptosis?",
        {},
        semantic_source_ids={"curcumin"},
        semantic_target_ids=set(),
    )
    _bonus, features = retriever._score_path_anchors(
        ["curcumin", "pyroptosis"], anchors
    )
    gate = retriever._classify_path_gate(
        ["curcumin", "pyroptosis"],
        [{"support_tier": "A", "directional": False}],
        features,
    )

    assert anchors["unresolved_target_endpoint"] is True
    assert gate["gate_tier"] == "C"
    assert "unresolved_target_endpoint" in gate["gate_reasons"]


def test_graph_builder_accumulates_aliases_across_articles():
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    builder._add_nodes(
        {
            "MESH:D006528_Disease": PubTatorNode(
                mesh="D006528",
                type="Disease",
                name="hcc",
                pmid="1",
                aliases={"HCC", "hepatocellular carcinoma"},
            )
        }
    )
    builder._add_nodes(
        {
            "MESH:D006528_Disease": PubTatorNode(
                mesh="D006528",
                type="Disease",
                name="liver cancer",
                pmid="2",
                aliases={"liver cancer"},
            )
        }
    )

    node = builder.graph.nodes["MESH:D006528_Disease"]
    assert node["aliases"] == {"HCC", "hepatocellular carcinoma", "liver cancer"}
    assert node["pmids"] == {"1", "2"}


def test_graph_rag_expands_generic_mirna_mechanism_anchor():
    graph = nx.Graph()
    graph.add_node("drug", name="Icariin", type="chemical")
    graph.add_node("mir153", name="miR-153", type="gene")
    graph.add_node("runx2", name="RUNX2", type="gene")
    retriever = GraphRetriever(graph)

    anchors = retriever._extract_query_anchors(
        "How may icariin act through miRNA-related mechanisms?", {}
    )

    assert anchors["source_ids"] == {"drug"}
    assert anchors["mechanism_ids"] == {"mir153"}
    assert anchors["target_ids"] == {"mir153"}


def test_graph_rag_normalizes_traditional_chinese_endpoint_terms():
    graph = nx.Graph()
    graph.add_node("drug", name="sglt2 inhibitor", type="chemical")
    graph.add_node("kidney", name="kidney diseases", type="disease")
    retriever = GraphRetriever(graph)

    query = "哪些中介機制可連結 SGLT2 抑制劑與腎臟保護？"

    assert set(retriever.find_relevant_nodes(query)) == {"drug", "kidney"}
    assert retriever._extract_endpoint_phrases(query) == (
        "sglt2 inhibitor",
        "kidney protection",
    )
    assert retriever._endpoint_lexically_compatible(
        "kidney protection", "kidney", graph.nodes["kidney"]
    ) is True


def test_claim_verifier_recognizes_amelioration_evidence_terms():
    assert relation_supported_by_text(
        "Exogenous ketone bodies protected the kidneys from injury.", "ameliorates"
    )
    assert relation_supported_by_text(
        "The intervention significantly improved renal fibrosis.", "ameliorates"
    )


def test_graph_rag_gate_marks_complete_aligned_path_claim_safe():
    retriever = _graph_retriever_with_supported_edge()

    context, paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="How does Drug inhibit Gene?", max_hops=1
    )

    assert paths[0]["gate_tier"] == "A"
    assert paths[0]["claim_safe"] is True
    assert paths[0]["retrieval_safe"] is True
    assert "[GATE TIER A; CLAIM-SAFE]" in context
    assert "[DIRECTIONAL MECHANISTIC EDGES: YES]" in context


def test_graph_rag_gate_keeps_incomplete_path_for_retrieval_only():
    graph = nx.Graph()
    graph.add_node("a", name="A", type="gene")
    graph.add_node("b", name="B", type="gene")
    graph.add_edge(
        "a",
        "b",
        edge_weight=1.0,
        relations={"1": {"activates"}},
        evidences={"1": {"activates": "A activates B."}},
    )

    context, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["a"], query="How does A activate B?", max_hops=1
    )

    assert paths[0]["gate_tier"] == "B"
    assert paths[0]["claim_safe"] is False
    assert paths[0]["retrieval_safe"] is True
    assert "[GATE TIER B; RETRIEVAL-ONLY]" in context
    assert "[DIRECTIONAL MECHANISTIC EDGES: NO]" in context


def test_graph_rag_gate_discards_contradicted_direction():
    graph = nx.Graph()
    graph.add_node("a", name="A", type="gene")
    graph.add_node("b", name="B", type="gene")
    graph.add_edge(
        "a",
        "b",
        edge_weight=1.0,
        source_id="b",
        relations={"1": {"activates"}},
        evidences={"1": {"activates": "B activates A."}},
        confidences={"1": {"activates": 0.9}},
    )

    context, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["a"], query="Does A activate B?", max_hops=1
    )

    assert paths[0]["gate_tier"] == "C"
    assert paths[0]["retrieval_safe"] is False
    assert "direction_contradicted_hop_1" in paths[0]["gate_reasons"]
    assert "[GATE TIER" not in context


def test_graph_rag_gate_downgrades_two_hop_path_with_weak_bridge_alignment():
    graph = nx.Graph()
    for node_id in ("source", "bridge", "target"):
        graph.add_node(node_id, name=node_id.title(), type="gene")
    for left, right in (("source", "bridge"), ("bridge", "target")):
        graph.add_edge(
            left,
            right,
            edge_weight=1.0,
            relations={"1": {"associated_with"}},
            evidences={"1": {"associated_with": f"{left} is associated with {right}."}},
            confidences={"1": {"associated_with": 0.9}},
        )

    _, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"], query="How does Source affect Target?", max_hops=2
    )
    path = next(
        item for item in paths if item["node_ids"] == ["source", "bridge", "target"]
    )

    assert path["gate_tier"] == "B"
    assert path["retrieval_safe"] is True
    assert path["claim_safe"] is False
    assert "weak_bridge_alignment" in path["gate_reasons"]


def test_graph_rag_gate_does_not_compose_treatment_edge_into_two_hop_mechanism():
    graph = nx.Graph()
    graph.add_node("source", name="Dysbiosis", type="disease")
    graph.add_node("bridge", name="Serotonin", type="chemical")
    graph.add_node("target", name="Bone Loss", type="disease")
    graph.add_edge(
        "source",
        "bridge",
        edge_weight=1.0,
        source_id="source",
        relations={"1": {"decreases"}},
        evidences={"1": {"decreases": "Dysbiosis decreases serotonin synthesis."}},
        confidences={"1": {"decreases": 0.9}},
    )
    graph.add_edge(
        "bridge",
        "target",
        edge_weight=1.0,
        source_id="bridge",
        relations={"2": {"treats"}},
        evidences={"2": {"treats": "Manipulating serotonin could treat bone loss."}},
        confidences={"2": {"treats": 0.9}},
    )

    _, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"],
        query="Which evidence-supported intermediates connect Dysbiosis to Bone Loss?",
        max_hops=2,
    )
    path = next(
        item for item in paths if item["node_ids"] == ["source", "bridge", "target"]
    )

    assert path["gate_tier"] == "B"
    assert path["retrieval_safe"] is True
    assert path["claim_safe"] is False
    assert "non_composable_intervention_hop_2" in path["gate_reasons"]


def test_graph_rag_recovers_bounded_four_hop_endpoint_mechanism():
    graph = nx.Graph()
    nodes = ["source", "bridge-a", "bridge-b", "bridge-c", "target"]
    names = ["Source Disease", "Viral Protein", "STAT1", "HKDC1", "Target Disease"]
    for node_id, name in zip(nodes, names):
        node_type = "disease" if "Disease" in name else "gene"
        if node_id == "bridge-a":
            node_type = "Species"
            name = "HBV"
        graph.add_node(node_id, name=name, type=node_type, aliases={name})
    relations = ["causes", "activates", "binds_to", "promotes"]
    quotes = [
        "Source Disease causes Viral Protein expression.",
        "Viral Protein activates STAT1 phosphorylation.",
        "STAT1 binds to HKDC1 in tumor cells.",
        "HKDC1 promotes Target Disease progression.",
    ]
    for index, (left, right) in enumerate(zip(nodes, nodes[1:]), start=1):
        relation = relations[index - 1]
        pmid = str(index)
        graph.add_edge(
            left,
            right,
            edge_weight=1.0,
            relations={pmid: {relation}},
            evidences={pmid: {relation: quotes[index - 1]}},
            confidences={pmid: {relation: 0.95}},
            source_id=left,
        )
    # Push the endpoint path below the ordinary top-60 score cutoff. It must
    # survive through the bounded, fully evidenced endpoint tail.
    for index in range(65):
        noise = f"noise-{index}"
        graph.add_node(noise, name=f"Noise {index}", type="gene")
        graph.add_edge(
            "source",
            noise,
            edge_weight=5.0,
            relations={f"n{index}": {"associated_with"}},
            evidences={f"n{index}": {"associated_with": "Source Disease is associated with noise."}},
            confidences={f"n{index}": {"associated_with": 0.95}},
        )

    context, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"],
        query="Which evidence-supported intermediates connect Source Disease to Target Disease?",
        max_hops=4,
    )
    path = next(item for item in paths if item["node_ids"] == nodes)

    assert path["gate_tier"] == "A"
    assert path["claim_safe"] is True
    assert path["hop_count"] == 4
    assert "bounded_mechanistic_multi_hop" in path["gate_reasons"]
    assert "HBV" in context


def test_graph_rag_long_path_rejects_unresolved_odd_inhibitory_polarity():
    graph = nx.Graph()
    nodes = ["source", "a", "b", "c", "target"]
    for node_id in nodes:
        graph.add_node(node_id, name=node_id.title(), type="gene")
    relations = ["causes", "inhibits", "binds_to", "promotes"]
    quotes = [
        "Source causes A expression.",
        "A inhibits B activity.",
        "B binds to C.",
        "C promotes Target progression.",
    ]
    for index, (left, right) in enumerate(zip(nodes, nodes[1:]), start=1):
        relation = relations[index - 1]
        pmid = str(index)
        graph.add_edge(
            left,
            right,
            edge_weight=1.0,
            relations={pmid: {relation}},
            evidences={pmid: {relation: quotes[index - 1]}},
            confidences={pmid: {relation: 0.95}},
            source_id=left,
        )

    _, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["source"], query="Which intermediates connect Source to Target?", max_hops=4
    )
    candidate = next(
        path for path in GraphRetriever(graph)._extract_top_k_paths(
            ["source"], "Which intermediates connect Source to Target?", 4, 60, True
        )
        if path["path"] == nodes
    )
    structured = GraphRetriever(graph)._build_structured_path_entry(candidate, 1)

    surfaced = next(path for path in paths if path["node_ids"] == nodes)
    assert surfaced["claim_safe"] is False
    assert structured["claim_safe"] is False
    assert "unresolved_path_polarity" in structured["gate_reasons"]


def test_graph_rag_species_filter_keeps_viral_pathogen_but_rejects_model_species():
    graph = nx.Graph()
    graph.add_node("virus", name="HBV", type="Species", aliases={"hepatitis B virus"})
    graph.add_node("mouse", name="Mus musculus", type="Species", aliases={"mouse"})
    retriever = GraphRetriever(graph)

    assert retriever._is_valid_node("virus") is True
    assert retriever._is_valid_node("mouse") is False


def test_graph_rag_zero_tier_a_rescue_recovers_lower_ranked_claim_safe_path():
    graph = nx.Graph()
    graph.add_node("source", name="Source", type="gene")
    graph.add_node("target", name="Target", type="gene")
    common = {
        "relations": {"1": {"activates"}},
        "evidences": {"1": {"activates": "Source activates the downstream target."}},
        "confidences": {"1": {"activates": 0.9}},
    }
    # Twenty-five high-scoring but query-misaligned candidates occupy the
    # strict top-20. The lower-scoring target is claim-safe and must be rescued.
    for index in range(25):
        node_id = f"noise-{index:02d}"
        graph.add_node(node_id, name=f"Noise {index:02d}", type="gene")
        graph.add_edge("source", node_id, edge_weight=1.0, **common)
    graph.add_edge("source", "target", edge_weight=0.1, **common)

    retriever = GraphRetriever(graph)
    context, paths = retriever.get_subgraph_context_with_paths(
        ["source"], query="How does Source activate Target?", max_hops=1
    )
    target_path = next(path for path in paths if path["node_ids"][-1] == "target")

    assert target_path["gate_tier"] == "A"
    assert target_path["rescue_triggered"] is True
    assert target_path["rescue_added"] is True
    assert target_path["candidate_rank"] > 20
    assert len(retriever.last_candidate_audit) == 26
    assert "OUTCOME: tier_a_recovered" in context
    assert "CLAIM-SAFE RESCUED" in context


def test_graph_rag_does_not_trigger_rescue_when_strict_pool_has_tier_a():
    retriever = _graph_retriever_with_supported_edge()

    context, paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="How does Drug inhibit Gene?", max_hops=1
    )

    assert paths[0]["rescue_triggered"] is False
    assert paths[0]["rescue_added"] is False
    assert paths[0]["rescue_outcome"] == "not_needed"
    assert "[ZERO-TIER-A RESCUE: NO; OUTCOME: not_needed]" in context


def test_graph_rag_adds_lower_ranked_claim_safe_novel_bridge_diversity():
    candidates = []
    for rank in range(1, 22):
        candidates.append(
            {
                "candidate_rank": rank,
                "node_ids": ["source", f"noise-{rank}"],
                "gate_tier": "A" if rank == 1 else "C",
                "claim_safe": rank == 1,
                "retrieval_safe": rank == 1,
            }
        )
    candidates.append(
        {
            "candidate_rank": 22,
            "node_ids": ["source", "novel-bridge", "target"],
            "gate_tier": "A",
            "claim_safe": True,
            "retrieval_safe": True,
        }
    )

    selected, rescue_triggered, outcome = GraphRetriever._select_gated_candidate_paths(
        candidates
    )

    added = next(path for path in selected if path.get("diversity_added"))
    assert rescue_triggered is False
    assert outcome == "not_needed"
    assert added["candidate_rank"] == 22
    assert len(selected) == 20


def test_claim_to_hop_verifier_accepts_causal_driver_wording():
    path = _claim_safe_test_path()
    path["relations"] = ["causes"]
    path["edge_evidence_quotes"] = [["Drug is a major driver of Gene activation."]]

    result = verify_claim_to_path(
        "Drug causes Gene [PMID: 12345678] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "supported"


def test_claim_to_hop_verifier_accepts_sufficient_to_alter_as_causal_evidence():
    path = _claim_safe_test_path()
    path["relations"] = ["causes"]
    path["edge_evidence_quotes"] = [
        ["Drug exposure is sufficient to alter Gene activity."]
    ]

    result = verify_claim_to_path(
        "Drug induces Gene changes [PMID: 12345678] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "supported"


def test_edge_support_downgrades_directional_relation_when_quote_lacks_relation():
    support = GraphRetriever._select_edge_support(
        {
            "relations": {"12345678": {"induces"}},
            "evidences": {
                "12345678": {
                    "induces": "Inflammation and viral integration participate in HCC pathogenesis."
                }
            },
            "confidences": {"12345678": {"induces": 0.95}},
        }
    )

    assert support["support_tier"] == "B"
    assert "quote_relation_mismatch" in support["support_reasons"]


def test_claim_to_hop_verifier_accepts_node_aliases():
    path = _claim_safe_test_path()
    path["names"] = ["CHB", "HCC"]
    path["node_aliases"] = [
        ["chronic hepatitis B", "chronic hepatitis B virus infection"],
        ["hepatocellular carcinoma"],
    ]
    path["relations"] = ["causes"]
    path["edge_evidence_quotes"] = [["CHB is a major driver of HCC."]]

    result = verify_claim_to_path(
        "Chronic hepatitis B causes hepatocellular carcinoma "
        "[PMID: 12345678] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "supported"


def test_answer_verifier_audits_every_path_reference_on_a_line():
    first = _claim_safe_test_path()
    second = dict(first)
    second["path_signature"] = "fed654cba321"

    result = verify_answer_graph_claims(
        "- Drug inhibits Gene [PMID: 12345678] "
        "PATH abc123def456; PATH fed654cba321",
        [first, second],
    )

    assert result["path_cited_claim_count"] == 2
    assert result["supported_claim_count"] == 2


def _claim_safe_test_path():
    retriever = _graph_retriever_with_supported_edge()
    _, paths = retriever.get_subgraph_context_with_paths(
        ["drug"], query="How does Drug inhibit Gene?", max_hops=1
    )
    path = paths[0]
    path["edge_pmids"] = [["12345678"]]
    path["path_signature"] = "abc123def456"
    path["path_id"] = "QTEST-P01"
    return path


def test_claim_to_hop_verifier_accepts_aligned_tier_a_claim():
    path = _claim_safe_test_path()

    result = verify_claim_to_path(
        "Drug inhibits Gene [PMID: 12345678] PATH abc123def456", "abc123def456", [path]
    )

    assert result["verdict"] == "supported"
    assert result["reasons"] == []


def test_claim_to_hop_verifier_accepts_relation_noun_form_in_quote():
    path = _claim_safe_test_path()
    path["relations"] = ["upregulates"]
    path["edge_evidence_quotes"] = [["Drug acts through upregulation of Gene."]]

    result = verify_claim_to_path(
        "Drug upregulates Gene [PMID: 12345678] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "supported"


def test_claim_to_hop_verifier_normalizes_underscored_relation_label():
    path = _claim_safe_test_path()
    path["relations"] = ["associated_with"]
    path["edge_evidence_quotes"] = [["Drug is associated with Gene activity."]]

    result = verify_claim_to_path(
        "Drug associated_with Gene [PMID: 12345678] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "supported"


def test_claim_to_hop_verifier_rejects_wrong_direction_relation_and_pmid():
    path = _claim_safe_test_path()

    result = verify_claim_to_path(
        "Gene activates Drug [PMID: 99999999] PATH abc123def456",
        "abc123def456",
        [path],
    )

    assert result["verdict"] == "unsupported"
    assert "hop_1_direction_mismatch" in result["reasons"]
    assert "hop_1_relation_mismatch" in result["reasons"]
    assert "hop_1_pmid_missing" in result["reasons"]


def test_claim_to_hop_verifier_rejects_retrieval_only_path():
    path = _claim_safe_test_path()
    path["gate_tier"] = "B"
    path["claim_safe"] = False

    result = verify_claim_to_path(
        "Drug inhibits Gene [PMID: 12345678] PATH QTEST-P01", "QTEST-P01", [path]
    )

    assert result["verdict"] == "unsupported"
    assert "path_not_tier_a_claim_safe" in result["reasons"]


def test_answer_claim_verifier_reports_missing_and_unsupported_path_citations():
    path = _claim_safe_test_path()
    answer = "\n".join(
        [
            "- Drug inhibits Gene [PMID: 12345678] PATH abc123def456",
            "- Drug activates Gene [PMID: 12345678] PATH missing999",
        ]
    )

    result = verify_answer_graph_claims(answer, [path])

    assert result["path_cited_claim_count"] == 2
    assert result["supported_claim_count"] == 1
    assert result["unsupported_claim_count"] == 1
    assert result["no_path_citations_detected"] is False


def test_answer_claim_verifier_does_not_treat_pathogenesis_as_path_reference():
    result = verify_answer_graph_claims(
        "IL-17 contributes to autoimmune pathogenesis [PMID: 12345678].", []
    )

    assert result["path_cited_claim_count"] == 0
    assert result["no_path_citations_detected"] is True


def test_frozen_pubtator_parser_recovers_literal_none_annotation_names():
    collection = PubTatorIO.parse(
        "evaluation/formal/runs/adaptive-replay-small-gpt41/questions/Q001/corpus.pubtator"
    )

    first = collection.articles[0].annotations[0]
    assert first.name == "Icariine"
    serialized = collection.to_pubtator_str(annotation_use_identifier_name=True)
    assert "\tNone\t" not in serialized


def test_frozen_pubtator_parser_restores_source_mirna_mention_from_offsets():
    collection = PubTatorIO.parse(
        "evaluation/formal/image_chain_acceptance_v1/corpus.pubtator"
    )
    article = next(item for item in collection.articles if item.pmid == "29500883")
    mirna_mentions = [
        annotation.name
        for annotation in article.annotations
        if annotation.mesh == "387211"
    ]

    assert "miR-21-5p" in mirna_mentions
    assert "Mir215" not in mirna_mentions


def test_google_prompt_uses_same_chatgpt_style_structure_as_openai():
    llm_client = SimpleNamespace(provider="google", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    prompt = extractor._build_llm_prompt(
        title="Example title",
        abstract="Example abstract text about retinal diseases and lutein.",
        entity_list=_sample_entities(),
    )

    assert "**Task**" in prompt
    assert "**Instructions**" in prompt
    assert "Return ONLY a JSON array" in prompt
    assert "Do NOT perform NER" in prompt


def test_openai_prompt_keeps_existing_structure():
    llm_client = SimpleNamespace(provider="openai", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    prompt = extractor._build_llm_prompt(
        title="Example title",
        abstract="Example abstract text about retinal diseases and lutein.",
        entity_list=_sample_entities(),
    )

    assert "**Task**" in prompt
    assert "Return ONLY a JSON array" in prompt
    assert "Do NOT perform NER" in prompt


def test_relaxed_parser_recovers_from_malformed_json_like_output():
    llm_client = SimpleNamespace(provider="google", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    malformed = """
[
  {"entity1_id":"MESH:D1_Disease","entity2_id":"MESH:D2_Chemical","relation_type":"associated_with","confidence":0.78,"evidence":"shows association}
]
"""
    rels = extractor._parse_llm_response_relaxed(malformed, "12345")
    assert len(rels) == 1
    assert rels[0]["entity1_id"] == "MESH:D1_Disease"
    assert rels[0]["entity2_id"] == "MESH:D2_Chemical"
    assert rels[0]["relation_type"] == "associated_with"


def test_google_effective_threshold_is_capped_for_gemini():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=None)
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)
    assert extractor._effective_confidence_threshold(0.5) == 0.25


def test_confidence_percent_is_normalized_and_kept_in_semantic_edge():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="12345",
        title="Example",
        abstract="Lutein is associated with retinal disease outcomes.",
    )
    nodes = {
        "MESH:D012559_Disease": SimpleNamespace(
            name="Retinal Diseases",
            type="Disease",
            mesh="D012559",
        ),
        "MESH:D007333_Chemical": SimpleNamespace(
            name="Lutein",
            type="Chemical",
            mesh="D007333",
        ),
    }

    extractor._call_llm = lambda prompt, *args, **kwargs: (
        '[{"entity1_id":"MESH:D012559_Disease","entity2_id":"MESH:D007333_Chemical",'
        '"relation_type":"associated_with","confidence":"78%","evidence":"associated"}]'
    )
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].confidence == 0.78


def _sample_article_and_nodes():
    article = SimpleNamespace(
        pmid="12345",
        title="Example",
        abstract="miR-153 directly targets Runx2 and reduces its expression.",
    )
    nodes = {
        "MESH:D1_Gene": SimpleNamespace(name="mir153", type="Gene", mesh="D1"),
        "MESH:D2_Gene": SimpleNamespace(name="runx2", type="Gene", mesh="D2"),
    }
    return article, nodes


def _extraction_response(relation_type: str) -> str:
    return (
        '[{"entity1_id":"MESH:D2_Gene","entity2_id":"MESH:D1_Gene",'
        f'"relation_type":"{relation_type}","confidence":0.9,'
        '"evidence":"miR-153 directly targets Runx2 and reduces its expression."}]'
    )


def test_verification_downgrades_reversed_directional_edge():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    calls = []

    def fake_call_llm(prompt, *args, **kwargs):
        calls.append(kwargs.get("client"))
        if kwargs.get("client") is not None:
            # Verification pass: the extractor claimed runx2 upregulates mir153, but the
            # evidence says mir153 targets/reduces runx2 -- direction is reversed.
            return '{"verifications": [{"index": 0, "direction_correct": 0}]}'
        return _extraction_response("upregulates")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].relation_type == "associated_with"  # downgraded, not dropped
    assert any(c is not None for c in calls)  # verification call actually happened
    assert extractor.last_run_stats["verification_downgrades"] == 1
    assert extractor.last_run_stats["verified_directional_edges"] == 1


def test_verification_keeps_correct_directional_edge():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        if kwargs.get("client") is not None:
            return '{"verifications": [{"index": 0, "direction_correct": 1}]}'
        return _extraction_response("inhibits")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].relation_type == "inhibits"  # kept, verification confirmed direction
    assert extractor.last_run_stats["verification_downgrades"] == 0


def test_verification_skipped_when_disabled():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=False
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        assert kwargs.get("client") is None, "verifier should never be called when disabled"
        return _extraction_response("inhibits")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].relation_type == "inhibits"


def test_verification_skipped_for_symmetric_relations():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        assert kwargs.get("client") is None, "symmetric relations should not be verified"
        return _extraction_response("associated_with")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].relation_type == "associated_with"


def test_verification_failure_leaves_edge_unchanged():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        if kwargs.get("client") is not None:
            raise RuntimeError("verifier API down")
        return _extraction_response("inhibits")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].relation_type == "inhibits"  # unchanged on verifier failure
    assert extractor.last_run_stats["verification_errors"] == 1


def test_verifier_llm_client_defaults_to_primary_client():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, verify_relations=True)
    assert extractor.verifier_llm_client is llm_client


def test_google_compact_retry_recovers_when_first_pass_empty():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="99999",
        title="Example",
        abstract="Chemical A inhibits Disease B progression.",
    )
    nodes = {
        "MESH:D_B_Disease": SimpleNamespace(name="Disease B", type="Disease", mesh="D_B"),
        "MESH:C_A_Chemical": SimpleNamespace(name="Chemical A", type="Chemical", mesh="C_A"),
    }

    calls = {"n": 0}

    def fake_call(prompt, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return "[]"
        return (
            '[{"entity1_id":"MESH:C_A_Chemical","entity2_id":"MESH:D_B_Disease",'
            '"relation_type":"inhibits","confidence":0.62}]'
        )

    extractor._call_llm = fake_call
    edges = extractor.analyze_article_relationships(article, nodes)

    assert calls["n"] == 2
    assert len(edges) == 1
    assert edges[0].relation_type == "inhibits"


def test_name_based_entity_fallback_is_not_allowed():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o-mini", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="77777",
        title="Example",
        abstract="Lutein is associated with retinal disease outcomes.",
    )
    nodes = {
        "MESH:D012559_Disease": SimpleNamespace(
            name="Retinal Diseases",
            type="Disease",
            mesh="D012559",
        ),
        "MESH:D007333_Chemical": SimpleNamespace(
            name="Lutein",
            type="Chemical",
            mesh="D007333",
        ),
    }

    # LLM returns names instead of canonical IDs; this should be rejected.
    extractor._call_llm = lambda prompt, *args, **kwargs: (
        '[{"entity1_id":"Retinal Diseases","entity2_id":"Lutein",'
        '"relation_type":"associated_with","confidence":0.92}]'
    )
    edges = extractor.analyze_article_relationships(article, nodes)
    assert len(edges) == 0


def test_relation_type_is_normalized_to_canonical_form():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o-mini", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)
    rels = extractor._parse_llm_response(
        '[{"entity1_id":"A","entity2_id":"B","relation_type":"inhibition","confidence":0.8}]',
        "pmid-x",
    )
    assert len(rels) == 1
    assert rels[0]["relation_type"] == "inhibits"


def test_google_coverage_prompt_is_valid():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    # This should not raise NameError: name 'pair_count' is not defined
    prompt = extractor._build_coverage_prompt(
        title="Example title",
        abstract="Example abstract text.",
        entity_list=_sample_entities(),
    )

    assert "unordered pairs" in prompt
    assert "one of:" in prompt
    assert "associated_with" in prompt


def test_verification_tolerates_trailing_brace_and_malformed_array():
    """Regression test for a real, reproducible Gemini-via-OpenAI-compat quirk: a stray extra
    closing brace after an otherwise well-formed JSON object, and separately a malformed array
    missing a comma between entries. Both must still recover a usable verdict."""
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        if kwargs.get("client") is not None:
            # Valid JSON with one stray trailing brace -- _loads_lenient/raw_decode must recover.
            return '{"verifications": [{"index": 0, "direction_correct": 0}]}\n}'
        return _extraction_response("upregulates")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert edges[0].relation_type == "associated_with"


def test_verification_regex_fallback_recovers_malformed_array():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    extractor = SemanticRelationshipExtractor(
        llm_client, confidence_threshold=0.5, verify_relations=True
    )
    article, nodes = _sample_article_and_nodes()

    def fake_call_llm(prompt, *args, **kwargs):
        if kwargs.get("client") is not None:
            # Missing comma before the closing bracket -- strict/lenient JSON parsing both fail,
            # only the regex fallback can recover this.
            return '{"verifications": [{"index": 0, "direction_correct": 0}'
        return _extraction_response("upregulates")

    extractor._call_llm = fake_call_llm
    edges = extractor.analyze_article_relationships(article, nodes)

    assert edges[0].relation_type == "associated_with"


def test_answer_claim_verifier_ignores_natural_language_path_label():
    result = verify_answer_graph_claims(
        "Path: dysbiosis leads to periodontitis and bone loss [PMID: 25918553].",
        [],
    )
    assert result["path_cited_claim_count"] == 0
    assert result["unsupported_claim_count"] == 0
