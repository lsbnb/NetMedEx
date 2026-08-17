import logging
import os
import pickle
import time
from unittest.mock import MagicMock

from netmedex.chat import ChatSession
from netmedex.graph_rag import GraphRetriever

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_stress_test():
    graph_path = "./data/pediatric_10k/graph.pkl"

    if not os.path.exists(graph_path):
        logger.error(f"Graph file {graph_path} not found. Skipping stress test.")
        return

    logger.info(f"Loading large graph: {graph_path}")
    start_time = time.time()
    with open(graph_path, "rb") as f:
        graph_data = pickle.load(f)

    # Handle different pickle formats (might be raw G or dict)
    if isinstance(graph_data, dict) and "graph" in graph_data:
        G = graph_data["graph"]
        documents = graph_data.get("pmid_abstract", {})
    else:
        G = graph_data
        documents = {}  # Fallback

    load_duration = time.time() - start_time
    logger.info(
        f"Loaded graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges in {load_duration:.2f}s"
    )

    # 1. Stress Test: Graph Retriever (2-Hop Logic)
    logger.info("--- Testing GraphRetriever (2-Hop Logic) ---")
    retriever = GraphRetriever(G)

    # Pick some high-degree nodes for heavy 2-hop traversal
    sample_nodes = sorted(G.degree, key=lambda x: x[1], reverse=True)[:10]
    sample_node_ids = [n[0] for n in sample_nodes]

    logger.info(f"Traversing 2-hop neighborhood for top 10 nodes: {sample_node_ids}")

    start_time = time.time()
    context = retriever.get_subgraph_context(sample_node_ids, max_hops=2)
    retrieval_duration = time.time() - start_time

    logger.info(f"2-Hop retrieval took {retrieval_duration:.2f}s")
    logger.info(f"Context length: {len(context)} characters")
    # logger.info(f"Context preview: {context[:500]}...")

    # 2. Stress Test: Chat Session (Mocked LLM)
    logger.info("--- Testing ChatSession Context Building ---")

    # Mock RAG system
    mock_rag = MagicMock()
    mock_rag.documents = documents
    # Simulate get_context returning some results
    mock_rag.get_context.return_value = ("Sample text context", list(documents.keys())[:10])

    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.provider = "openai"
    mock_llm.model = "gpt-4o-mini"
    mock_llm.chat_completion_text.return_value = (
        "<thinking_english>Reasoning...</thinking_english>證據分析: Success! [PMID:123]"
    )

    session = ChatSession(mock_rag, mock_llm, graph_retriever=retriever)

    logger.info("Sending complex query to session...")
    start_time = time.time()
    response = session.send_message(
        "Summarize the 2-hop relationships between the top genes.", top_k=20
    )
    chat_duration = time.time() - start_time

    logger.info(f"Chat context building and mock call took {chat_duration:.2f}s")
    logger.info(f"Response Success: {response['success']}")

    logger.info("--- Stress Test Completed ---")


if __name__ == "__main__":
    run_stress_test()
