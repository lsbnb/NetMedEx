import networkx as nx

from netmedex.hybrid_retrieval import (
    PersistentGraphCache,
    build_pubmed_expansion_queries,
    filter_expansion_paths,
    merge_expanded_ranking,
    route_query,
)


def _path(bridge="AMPK", pmids=None, retrieval_safe=True):
    return {
        "names": ["metformin", bridge, "autophagy"],
        "edge_pmids": pmids or [["1"], ["2"]],
        "retrieval_safe": retrieval_safe,
    }


def test_router_only_enables_graph_for_multi_hop_intent():
    assert route_query("mechanism", "plain").use_graph
    assert route_query("discovery", "plain").use_graph
    assert not route_query("direct_evidence", "mechanism word in metadata-controlled item").use_graph
    assert not route_query("association", "plain").use_graph
    assert route_query("", "Find a two-hop mediator").use_graph


def test_expansion_gate_requires_specific_cross_document_path():
    assert filter_expansion_paths([_path()])
    assert not filter_expansion_paths([_path(bridge="signaling")])
    assert not filter_expansion_paths([_path(pmids=[["1"], ["1"]])])
    assert not filter_expansion_paths([_path(retrieval_safe=False)])


def test_expansion_queries_are_bounded_and_include_endpoint_pair():
    queries = build_pubmed_expansion_queries([_path()], max_queries=2)
    assert queries == [
        '"metformin"[Title/Abstract] AND "autophagy"[Title/Abstract]',
        '"metformin"[Title/Abstract] AND "AMPK"[Title/Abstract]',
    ]


def test_persistent_graph_cache_round_trip(tmp_path):
    cache = PersistentGraphCache(tmp_path)
    graph = nx.Graph()
    graph.add_edge("A", "B", relation="activates")
    config = {"model": "test", "threshold": 0.8}
    key = cache.key(b"corpus", config)
    assert cache.load(key) is None
    cache.store(key, graph, config)
    loaded = cache.load(key)
    assert loaded is not None
    assert loaded.edges["A", "B"]["relation"] == "activates"


def test_expansion_merge_protects_head_and_requires_margin():
    original = [(str(i), 1.0 - i / 100) for i in range(10)]
    expanded = original + [("new-strong", 1.2), ("new-weak", 0.90)]
    merged, audit = merge_expanded_ranking(
        original, expanded, {"new-strong", "new-weak"}, top_k=10
    )
    assert {str(i) for i in range(8)} <= {pmid for pmid, _score in merged}
    assert "new-strong" in dict(merged)
    assert "new-weak" not in dict(merged)
    assert audit["accepted_added_pmids"] == ["new-strong"]
