import networkx as nx

from evaluation.run_formal_50 import (
    _path_to_evidence_text,
    adaptive_route_for_question,
    classify_incremental_path_value,
    evidence_strength_by_pmid,
    enrich_query_metadata,
    filter_frozen_paths_for_profile,
    load_queries,
    generate_answer,
    graph_retrieval_query,
    rerank_with_evidence_gate,
    decide_hybrid_integration,
    require_nonempty_semantic_graph,
    resolve_hybrid_profile,
    select_hybrid_exposure,
)


def test_graph_retrieval_query_adds_non_gold_english_terms_for_chinese():
    row = {
        "question": "請找出抗纖維化機制。",
        "language": "Traditional Chinese",
        "pubmed_query": "SGLT2 inhibitor AND (kidney OR fibrosis)",
    }

    query = graph_retrieval_query(row)

    assert query.startswith(row["question"])
    assert "SGLT2 inhibitor" in query
    assert "kidney fibrosis" in query
    assert " AND " not in query


def test_graph_retrieval_query_leaves_english_question_unchanged():
    row = {
        "question": "How does A affect B?",
        "language": "English",
        "pubmed_query": "A AND B",
    }

    assert graph_retrieval_query(row) == row["question"]


def test_live_semantic_graph_build_fails_closed_on_empty_graph():
    try:
        require_nonempty_semantic_graph(nx.Graph(), 26)
    except RuntimeError as exc:
        assert "probable provider or extraction failure" in str(exc)
    else:
        raise AssertionError("empty semantic graph should fail closed")

    require_nonempty_semantic_graph(nx.Graph(), 0)


def test_adaptive_router_uses_frozen_question_type():
    assert adaptive_route_for_question("mechanism", "plain wording")[0] == "H_evidence_gated_four_hop"
    assert adaptive_route_for_question("association", "plain wording")[0] == "A_text_only"
    assert adaptive_route_for_question("direct_evidence", "plain wording")[0] == "A_text_only"


def test_adaptive_router_conservative_keyword_fallback():
    assert adaptive_route_for_question("", "Which genes mediate a possible 2-hop path?")[0] == "H_evidence_gated_four_hop"
    assert adaptive_route_for_question("", "What evidence supports this treatment?")[0] == "A_text_only"


def test_resolve_profile_keeps_fixed_arm_and_routes_adaptive_arm():
    assert resolve_hybrid_profile("C_one_hop", "mechanism", "question") == (
        "C_one_hop",
        "fixed profile",
    )
    assert resolve_hybrid_profile("F_adaptive", "retrieval", "question")[0] == "A_text_only"


def test_enrich_query_metadata_only_attaches_question_type(tmp_path):
    metadata = tmp_path / "questions.csv"
    metadata.write_text(
        "question_id,question_type,gold_pmids\nQ001,mechanism,should-not-leak\n",
        encoding="utf-8",
    )
    rows = [{"question_id": "Q001", "question": "Question"}]
    enriched = enrich_query_metadata(rows, metadata)
    assert enriched[0]["question_type"] == "mechanism"
    assert "gold_pmids" not in enriched[0]


def test_query_loader_accepts_explicit_nonformal_batch_size(tmp_path):
    queries = tmp_path / "queries.csv"
    queries.write_text(
        "question_id,domain,question,pubmed_query,language\n"
        "BW001,test,Question one,query one,English\n"
        "BW002,test,Question two,query two,English\n",
        encoding="utf-8",
    )

    rows = load_queries(queries, expected_count=2)

    assert [row["question_id"] for row in rows] == ["BW001", "BW002"]


def test_evidence_gated_profile_drops_paths_with_an_unsupported_hop():
    supported = {
        "names": ["A", "B", "C"],
        "relations": ["activates", "inhibits"],
        "edge_pmids": [["1"], ["2"]],
        "edge_is_directional": [True, True],
        "edge_evidence_complete": [True, True],
        "score": 0.9,
    }
    unsupported = {
        **supported,
        "names": ["A", "X", "C"],
        "edge_evidence_complete": [True, False],
    }

    class Retriever:
        def find_relevant_nodes(self, _question):
            return ["A"]

        def get_subgraph_context_with_paths(self, *_args, **_kwargs):
            return "raw", [supported, unsupported]

    context, paths, pmids, exposure = select_hybrid_exposure(
        "G_evidence_gated_two_hop", Retriever(), nx.Graph(), "question"
    )
    assert paths == [supported]
    assert pmids == {"1", "2"}
    assert "A ->[activates] B" in context
    assert exposure["gate_evidence_paths"] is True


def test_evidence_strength_ignores_paths_with_an_unsupported_hop():
    paths = [
        {
            "score": 0.95,
            "edge_pmids": [["1"], ["2"]],
            "edge_evidence_complete": [True, True],
        },
        {
            "score": 1.0,
            "edge_pmids": [["3"], ["4"]],
            "edge_evidence_complete": [True, False],
        },
    ]
    assert evidence_strength_by_pmid(paths) == {"1": 0.95, "2": 0.95}


def test_frozen_replay_reapplies_live_evidence_gate():
    paths = [
        {
            "path_id": "A",
            "retrieval_safe": True,
            "claim_safe": True,
            "edge_evidence_complete": [True, True],
        },
        {
            "path_id": "B",
            "retrieval_safe": True,
            "claim_safe": False,
            "edge_evidence_complete": [True],
        },
        {
            "path_id": "C",
            "retrieval_safe": False,
            "claim_safe": False,
            "edge_evidence_complete": [True],
        },
    ]

    filtered = filter_frozen_paths_for_profile(
        paths, {"gate_evidence_paths": True}
    )

    assert [path["path_id"] for path in filtered] == ["A"]


def test_frozen_replay_demotes_low_confidence_quote_to_retrieval_only():
    path = {
        "path_id": "low-confidence",
        "gate_tier": "A",
        "retrieval_safe": True,
        "claim_safe": True,
        "edge_evidence_complete": [True],
        "edge_supports": [
            {
                "selected_quote": "A activated B.",
                "quote_relation_aligned": True,
                "selected_confidence": 0.79,
            }
        ],
    }

    assert filter_frozen_paths_for_profile(
        [path], {"gate_evidence_paths": True}
    ) == []
    retrieval_only = filter_frozen_paths_for_profile(
        [path], {"gate_evidence_paths": False}
    )
    assert retrieval_only[0]["gate_tier"] == "B"
    assert retrieval_only[0]["claim_safe"] is False


def test_incremental_path_requires_unseen_bridge_and_outside_support():
    path = {
        "node_ids": ["source", "bridge", "target"],
        "names": ["Drug", "Novel kinase", "Disease"],
        "node_aliases": [[], ["NK-1"], []],
        "edge_pmids": [["1"], ["99"]],
        "claim_safe": True,
    }

    audit = classify_incremental_path_value(
        [path], [("1", 0.9), ("2", 0.8)], "Drug and Disease were studied.", "Drug to Disease?"
    )

    assert path["incremental_value_class"] == "graph_incremental_candidate"
    assert path["supporting_pmids_outside_text_top_k"] == ["99"]
    assert audit["graph_incremental_candidate_count"] == 1
    assert path["mechanism_utility_score"] > path["path_relevance_score"] * 0.55


def test_three_stage_router_uses_evidence_value_not_question_type_alone():
    assert decide_hybrid_integration([])["mode"] == "traditional_fallback"
    confirmed = {"gate_tier": "A", "claim_safe": True, "edge_pmids": [["1"]],
                 "incremental_value_class": "graph_confirmed"}
    assert decide_hybrid_integration([confirmed])["mode"] == "citation_validation"
    incremental = dict(confirmed, incremental_value_class="graph_incremental_candidate")
    assert decide_hybrid_integration([confirmed, incremental])["mode"] == "full_hybrid"


def test_incremental_path_keeps_outside_hop_when_bridge_visible_in_text():
    path = {
        "node_ids": ["source", "bridge", "target"],
        "names": ["Drug", "AMPK", "mTOR"],
        "node_aliases": [[], [], []],
        "edge_pmids": [["1"], ["99"]],
        "claim_safe": True,
    }

    classify_incremental_path_value(
        [path],
        [("1", 0.9)],
        "Metformin activates AMPK.",
        "How does Drug affect mTOR through AMPK?",
    )

    assert path["incremental_value_class"] == "graph_incremental_candidate"
    assert path["incremental_value_subtype"] == "retrieval_incremental_bridge_visible"
    assert "bridge_visible_in_text" in path["incremental_value_reasons"]


def test_incremental_path_requires_requested_bridge_alignment():
    wrong = {
        "node_ids": ["cftr", "dysbiosis", "inflammation"],
        "names": ["CFTR", "dysbiosis", "inflammation"],
        "node_aliases": [[], [], []],
        "edge_pmids": [["1"], ["99"]],
        "claim_safe": True,
        "score": 0.9,
    }
    right = {
        "node_ids": ["cftr", "cystic-fibrosis", "inflammation"],
        "names": ["CFTR", "cystic fibrosis", "inflammation"],
        "node_aliases": [[], [], []],
        "edge_pmids": [["1"], ["98"]],
        "claim_safe": True,
        "score": 0.7,
    }
    classify_incremental_path_value(
        [wrong, right],
        [("1", 0.9)],
        "CFTR and inflammation evidence.",
        "What path connects CFTR to inflammation through cystic fibrosis?",
    )
    assert wrong["incremental_value_class"] == "graph_confirmed"
    assert wrong["requested_bridge_coverage"] == 0
    assert right["incremental_value_class"] == "graph_incremental_candidate"
    assert right["requested_bridge_coverage"] == 1


def test_incremental_path_bridge_visibility_ignores_ontology_word_order():
    path = {
        "node_ids": ["source", "bridge", "target"],
        "names": ["HBV", "hepatitis chronic", "HCC"],
        "node_aliases": [[], [], []],
        "edge_pmids": [["1"], ["99"]],
        "claim_safe": True,
    }

    classify_incremental_path_value(
        [path],
        [("1", 0.9)],
        "Chronic hepatitis causes progressive liver injury.",
        "How does HBV lead to HCC?",
    )

    assert path["incremental_value_class"] == "graph_incremental_candidate"
    assert path["incremental_value_subtype"] == "retrieval_incremental_bridge_visible"
    assert "bridge_visible_in_text" in path["incremental_value_reasons"]


def test_evidence_reranker_requires_margin_and_blends_instead_of_multiplying():
    text = [("strong_text", 0.80), ("boost_me", 0.70), ("weak_path", 0.69)]
    paths = [
        {
            "score": 1.0,
            "edge_pmids": [["boost_me"]],
            "edge_evidence_complete": [True],
        },
        {
            "score": 0.80,
            "edge_pmids": [["weak_path"]],
            "edge_evidence_complete": [True],
        },
    ]
    ranking, audit = rerank_with_evidence_gate(text, paths, top_k=3)
    assert ranking == [
        ("boost_me", 0.8049999999999999),
        ("strong_text", 0.80),
        ("weak_path", 0.69),
    ]
    assert set(audit["boosted_pmids"]) == {"boost_me"}


def test_evidence_reranker_uses_combined_mechanism_utility_when_available():
    ranking, audit = rerank_with_evidence_gate(
        [("incremental", 0.50), ("semantic_only", 0.70)],
        [
            {
                "score": 0.60,
                "mechanism_utility_score": 0.90,
                "edge_pmids": [["incremental"]],
                "edge_evidence_complete": [True],
            }
        ],
        top_k=2,
    )
    assert ranking[0][0] == "semantic_only"
    assert ranking[1][1] > 0.50
    assert audit["method"] == "relevance_incremental_mechanism_blend_v1"


def test_graph_prompt_context_includes_path_pmids_and_quotes():
    rendered = _path_to_evidence_text(
        {
            "names": ["A", "B"],
            "relations": ["activates"],
            "edge_pmids": [["12345"]],
            "edge_evidence_quotes": [["A directly activates B in treated cells."]],
            "score": 0.91,
            "hop_count": 1,
        }
    )
    assert "PATH " in rendered
    assert "A ->[activates] B" in rendered
    assert "PMIDs: 12345" in rendered
    assert 'EVIDENCE: "A directly activates B in treated cells."' in rendered


def test_hybrid_answer_prompt_forbids_graph_claims_when_no_paths_are_supplied():
    class CapturingLLM:
        def chat_completion_text(self, *, messages, **_kwargs):
            self.messages = messages
            return "answer"

    llm = CapturingLLM()
    generate_answer(
        llm,
        system="netmedex_hybrid_rag",
        question="question",
        language="English",
        text_context="PMID: 1",
        graph_context="",
    )
    assert "No graph paths were supplied" in llm.messages[0]["content"]
    assert "Do not create PATH identifiers" in llm.messages[0]["content"]
