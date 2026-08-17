import networkx as nx

from netmedex.graph_rag import GraphRetriever
from netmedex.chat import ChatSession


def _add_gene(graph, node_id):
    graph.add_node(node_id, name=node_id, type="Gene", pmids=set())


def test_path_ranking_uses_nested_semantic_confidences():
    graph = nx.Graph()
    for node_id in ("A", "high", "low"):
        _add_gene(graph, node_id)
    common = {
        "edge_weight": 1.0,
        "relations": {"1": {"associated_with"}},
        "evidences": {"1": {"associated_with": "supported quote"}},
    }
    graph.add_edge(
        "A",
        "high",
        **common,
        confidences={"1": {"associated_with": 0.95}},
    )
    graph.add_edge(
        "A",
        "low",
        **common,
        confidences={"1": {"associated_with": 0.10}},
    )

    _context, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["A"], query="A", max_hops=1
    )

    assert paths[0]["names"] == ["A", "high"]
    assert paths[0]["score"] > paths[1]["score"]


def test_score_edge_components_reproduces_final_path_score():
    graph = nx.Graph()
    for node_id in ("A", "high"):
        _add_gene(graph, node_id)
    graph.add_edge(
        "A",
        "high",
        edge_weight=1.0,
        relations={"1": {"associated_with"}},
        evidences={"1": {"associated_with": "supported quote"}},
        confidences={"1": {"associated_with": 0.95}},
    )

    retriever = GraphRetriever(graph)
    _context, paths = retriever.get_subgraph_context_with_paths(["A"], query="A", max_hops=1)

    components = retriever.score_edge_components(
        "A", "high", graph.edges["A", "high"], max_edge_weight=1.0, semantic_relevance_map={}
    )

    # score_edge_components is the single source of truth calculate_score delegates to --
    # recomposing base_score * ontology_multiplier from its raw parts must reproduce the
    # actual path score exactly, and the weighted sum must match the documented 0.3/0.4/0.3 split.
    assert round(components["final_score"], 3) == paths[0]["score"]
    assert components["base_score"] == (
        components["npmi"] * 0.3 + components["calibrated_conf"] * 0.4 + components["rel_score"] * 0.3
    )
    assert components["final_score"] == components["base_score"] * components["ontology_multiplier"]


def test_production_graph_context_includes_pmid_linked_evidence_quote():
    graph = nx.Graph()
    for node_id in ("A", "B"):
        _add_gene(graph, node_id)
    graph.add_edge(
        "A",
        "B",
        edge_weight=1.0,
        relations={"12345": {"activates"}},
        evidences={"12345": {"activates": "A directly activates B after treatment."}},
        confidences={"12345": {"activates": 0.95}},
    )

    context, paths = GraphRetriever(graph).get_subgraph_context_with_paths(
        ["A"], query="A activates B", max_hops=1
    )

    assert "PMID:12345" in context
    assert "relation=activates" in context
    assert "quote=A directly activates B after treatment." in context
    assert paths[0]["edge_evidence_complete"] == [True]

    class DummyLLM:
        provider = "openai"

    messages = ChatSession(None, DummyLLM())._build_messages(
        "Does A activate B?",
        "PMID: 12345\nAbstract: A directly activates B after treatment.",
        context,
    )
    final_prompt = messages[-1]["content"]
    assert "Knowledge Graph Structure:" in final_prompt
    assert "PMID:12345; relation=activates" in final_prompt
    assert "quote=A directly activates B after treatment." in final_prompt
