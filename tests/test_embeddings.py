import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.append(os.getcwd())

from webapp.llm import ANTHROPIC_BASE_URL, OPENAI_BASE_URL, LLMClient


def test_get_embeddings():
    # Initialize client
    client = LLMClient()

    # Mock client and api key
    client.api_key = "mock-api-key"
    mock_openai = MagicMock()
    client.client = mock_openai

    # Mock response
    mock_embedding_1 = MagicMock()
    mock_embedding_1.embedding = [0.1, 0.2, 0.3]

    mock_embedding_2 = MagicMock()
    mock_embedding_2.embedding = [0.4, 0.5, 0.6]

    mock_response = MagicMock()
    mock_response.data = [mock_embedding_1, mock_embedding_2]

    mock_openai.embeddings.create.return_value = mock_response

    # Call get_embeddings
    texts = ["hello", "world"]
    embeddings = client.get_embeddings(texts)

    # Assertions
    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_openai.embeddings.create.assert_called_once_with(
        input=texts,
        model=client.embedding_model,
        timeout=60.0,
    )


def test_get_embeddings_empty():
    client = LLMClient()
    client.api_key = "mock-api-key"
    client.client = MagicMock()

    assert client.get_embeddings([]) == []


def test_get_embeddings_uninitialized():
    client = LLMClient()
    client.api_key = None
    client.client = None

    with pytest.raises(ValueError, match="key is not configured"):
        client.get_embeddings(["test"])


def test_switching_provider_resets_default_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = LLMClient()
    assert client.base_url == ANTHROPIC_BASE_URL

    client.initialize_client(provider="openai")

    assert client.base_url == OPENAI_BASE_URL


def test_get_embeddings_batching():
    client = LLMClient()
    client.api_key = "mock-api-key"
    mock_openai = MagicMock()
    client.client = mock_openai

    # Let's generate 150 texts (larger than 128 batch size)
    texts = [f"text_{i}" for i in range(150)]

    # Mock response for batch 1 (128 items)
    mock_embedding_batch1 = [MagicMock(embedding=[float(i)] * 3) for i in range(128)]
    mock_response_1 = MagicMock()
    mock_response_1.data = mock_embedding_batch1

    # Mock response for batch 2 (22 items)
    mock_embedding_batch2 = [MagicMock(embedding=[float(i)] * 3) for i in range(128, 150)]
    mock_response_2 = MagicMock()
    mock_response_2.data = mock_embedding_batch2

    mock_openai.embeddings.create.side_effect = [mock_response_1, mock_response_2]

    embeddings = client.get_embeddings(texts)

    assert len(embeddings) == 150
    assert embeddings[0] == [0.0, 0.0, 0.0]
    assert embeddings[149] == [149.0, 149.0, 149.0]

    assert mock_openai.embeddings.create.call_count == 2


def test_normalize_knowledge_graph_integration():
    import networkx as nx

    from netmedex.normalization import normalize_knowledge_graph

    # Create a small graph with 2 nodes that should merge
    G = nx.Graph()
    G.add_node("node1", name="HCV", type="Disease", mesh="D019698")
    G.add_node("node2", name="Hepatitis C Virus", type="Disease", mesh="D019698")
    # Add a normal/other node
    G.add_node("some_other_node", name="Other", type="Disease")
    G.add_edge("node1", "some_other_node")

    # Mock llm_client
    mock_llm = MagicMock()
    mock_llm.provider = "openai"
    mock_llm.model = "gpt-4o"
    mock_llm.get_embeddings.return_value = [[0.1, 0.2], [0.1, 0.201], [0.8, 0.9]]

    # Call normalize_knowledge_graph
    normalized_G = normalize_knowledge_graph(G, mock_llm, threshold=0.95)

    # Let's verify that get_embeddings was called, and that node merge happened.
    assert mock_llm.get_embeddings.called
    assert normalized_G.number_of_nodes() < G.number_of_nodes()
