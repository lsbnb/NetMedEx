import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from netmedex.chat import ChatSession
from netmedex.fastapi_bridge import _SessionStore, create_app
from netmedex.graph import PubTatorGraphBuilder
from netmedex.npmi import normalized_pointwise_mutual_information
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


def test_session_store_lru():
    """Test that _SessionStore evicts oldest sessions when max_sessions is reached."""
    store = _SessionStore(max_sessions=3, ttl_seconds=3600)
    b1, b2, b3, b4 = MagicMock(), MagicMock(), MagicMock(), MagicMock()

    s1 = store.create(b1, {"name": "s1"})
    time.sleep(0.01)
    s2 = store.create(b2, {"name": "s2"})
    time.sleep(0.01)
    s3 = store.create(b3, {"name": "s3"})

    meta = store.list_meta()
    assert len(meta) == 3
    assert s1 in meta and s2 in meta and s3 in meta

    # Access s1 to make s2 the oldest
    _ = store.get(s1)
    time.sleep(0.01)

    # Creating s4 should evict s2 (oldest last_accessed)
    s4 = store.create(b4, {"name": "s4"})
    meta_after = store.list_meta()
    assert len(meta_after) == 3
    assert s2 not in meta_after
    assert s1 in meta_after
    assert s3 in meta_after
    assert s4 in meta_after

    with pytest.raises(KeyError):
        store.get(s2)


def test_session_store_ttl_expiration():
    """Test that expired sessions are automatically evicted."""
    store = _SessionStore(max_sessions=10, ttl_seconds=1)  # 1 second TTL
    b1 = MagicMock()
    s1 = store.create(b1, {"name": "s1"})

    assert store.get(s1) is b1

    # Wait for TTL to expire
    time.sleep(1.1)

    meta = store.list_meta()
    assert s1 not in meta
    with pytest.raises(KeyError):
        store.get(s1)


def test_graph_builder_none_extractor_error():
    """Test that PubTatorGraphBuilder raises ImportError if SemanticRelationshipExtractor is None."""
    with patch("netmedex.graph.SemanticRelationshipExtractor", None):
        with pytest.raises(ImportError, match="SemanticRelationshipExtractor is not available"):
            PubTatorGraphBuilder(
                node_type="all",
                edge_method="semantic",
                llm_client=MagicMock(),
            )


def test_graph_builder_lifecycle_protection():
    """Test lifecycle state protection on PubTatorGraphBuilder."""
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")

    # 0 articles build returns empty graph
    g0 = builder.build()
    assert len(g0.nodes) == 0

    # Add article
    article = PubTatorArticle(
        pmid="12345678",
        date="2024",
        journal="Nature",
        doi=None,
        title="Sample Title",
        abstract="Sample Abstract",
        annotations=[
            PubTatorAnnotation(
                pmid="12345678",
                start=0,
                end=5,
                name="GeneA",
                identifier_name="GeneA",
                type="Gene",
                mesh="1001",
            ),
            PubTatorAnnotation(
                pmid="12345678",
                start=10,
                end=15,
                name="DiseaseB",
                identifier_name="DiseaseB",
                type="Disease",
                mesh="D0001",
            ),
        ],
        relations=[],
    )
    builder.add_article(article)
    assert builder._updated is True
    assert builder._is_built is False

    g1 = builder.build()
    assert builder._is_built is True
    assert builder._updated is False

    # Second build call without updates should safely return g1 without error or re-pruning
    g2 = builder.build()
    assert g2 is g1

    # Adding an article after build resets _is_built
    builder.add_article(article)
    assert builder._is_built is False
    assert builder._updated is True


def test_graph_builder_records_edge_method_on_graph_metadata():
    """Chat's send_message needs graph.graph['edge_method'] to decide whether
    suggesting a rebuild with Semantic Analysis would actually help (see
    suggest_semantic_edge_method in chat.py) -- so the builder must stamp it."""
    builder = PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")
    assert builder.graph.graph["edge_method"] == "co-occurrence"


def test_npmi_floating_boundary():
    """Test NPMI calculation precision at extreme boundary conditions."""
    # Complete co-occurrence: n_xy == N
    score_exact = normalized_pointwise_mutual_information(
        n_x=10, n_y=10, n_xy=10, N=10, n_threshold=2
    )
    assert score_exact == 1.0

    # Slight floating point deviation where n_xy / N is 0.9999999999999999
    score_close = normalized_pointwise_mutual_information(
        n_x=10.0, n_y=10.0, n_xy=9.999999999999999, N=10, n_threshold=2
    )
    assert score_close == 1.0

    # Zero co-occurrence (n_xy <= 0 returns below_threshold_default = 0.0)
    score_zero = normalized_pointwise_mutual_information(
        n_x=10, n_y=10, n_xy=0, N=10, n_threshold=2
    )
    assert score_zero == 0.0

    # Non-positive input guard
    score_neg = normalized_pointwise_mutual_information(
        n_x=-1, n_y=10, n_xy=5, N=10, n_threshold=2
    )
    assert score_neg == 0.0


def test_chat_context_budget_truncation():
    """Test that oversized context is truncated gracefully in _build_messages."""
    llm_mock = MagicMock()
    llm_mock.provider = "local"
    rag_mock = MagicMock()
    session = ChatSession(llm_client=llm_mock, rag_system=rag_mock, topic="Osteoporosis")

    huge_graph = "NodeA --[binds]--> NodeB\n" * 1000  # ~25k chars
    huge_abstracts = "PMID: 10001 Abstract text with detailed content.\n" * 1000  # ~50k chars

    messages = session._build_messages(
        user_message="Explain mechanism",
        text_context=huge_abstracts,
        graph_context=huge_graph,
        session_language="English",
    )

    user_msg_content = messages[-1]["content"]
    assert "[... Graph context truncated to fit context budget ...]" in user_msg_content
    assert "[... Abstract context truncated to fit context budget ...]" in user_msg_content
    # Overall user message should be kept well under local context budget
    assert len(user_msg_content) < 20000


def test_fastapi_bridge_no_key_configured_allows_all_requests(monkeypatch):
    """With NETMEDEX_API_KEY unset (today's default), /sessions must stay unauthenticated --
    this is the local-single-user case and must see zero behavior change."""
    monkeypatch.delenv("NETMEDEX_API_KEY", raising=False)
    client = TestClient(create_app())
    resp = client.get("/sessions")
    assert resp.status_code == 200


def test_fastapi_bridge_rejects_missing_or_wrong_key(monkeypatch):
    """With NETMEDEX_API_KEY set, protected routes must 401 without it or with the wrong value."""
    monkeypatch.setenv("NETMEDEX_API_KEY", "s3cr3t")
    client = TestClient(create_app())

    resp_no_key = client.get("/sessions")
    assert resp_no_key.status_code == 401

    resp_wrong_key = client.get("/sessions", headers={"X-API-Key": "wrong"})
    assert resp_wrong_key.status_code == 401

    resp_wrong_bearer = client.get("/sessions", headers={"Authorization": "Bearer wrong"})
    assert resp_wrong_bearer.status_code == 401


def test_fastapi_bridge_accepts_correct_key_via_header_or_bearer(monkeypatch):
    """The correct key must be accepted via either X-API-Key or an Authorization bearer token."""
    monkeypatch.setenv("NETMEDEX_API_KEY", "s3cr3t")
    client = TestClient(create_app())

    resp_header = client.get("/sessions", headers={"X-API-Key": "s3cr3t"})
    assert resp_header.status_code == 200

    resp_bearer = client.get("/sessions", headers={"Authorization": "Bearer s3cr3t"})
    assert resp_bearer.status_code == 200


def test_fastapi_bridge_health_never_requires_a_key(monkeypatch):
    """/health must stay reachable with no key even when NETMEDEX_API_KEY is set, so uptime
    probes/orchestrators don't need a credential just to check liveness."""
    monkeypatch.setenv("NETMEDEX_API_KEY", "s3cr3t")
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
