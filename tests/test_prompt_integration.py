import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from netmedex.chat import ChatSession, ChatMessage
from netmedex.rag import AbstractDocument


def test_prompt_structure():
    print("Testing Prompt Structure...")

    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.provider = "openai"
    mock_llm.model = "gpt-4o"

    # Mock RAG System
    mock_rag = MagicMock()
    doc1 = AbstractDocument(
        pmid="12345678",
        title="Test Paper",
        abstract="Icariin promotes osteoblast differentiation.",
        entities=[],
        edges=[],
        weight=1.0,
    )
    mock_rag.documents = {"12345678": doc1}
    mock_rag.get_context.return_value = (
        "PMID: 12345678\nTitle: Test Paper\nAbstract: Icariin promotes osteoblast differentiation.",
        ["12345678"],
    )

    # Initialize Session
    session = ChatSession(mock_rag, mock_llm, topic="osteoporosis therapy")

    # Test message building
    messages = session._build_messages(
        "How does icariin help?", "PMID: 12345678\nAbstract: ...", "", "English"
    )

    system_msg = messages[0]["content"]
    user_msg = messages[-1]["content"]

    assert "focusing on osteoporosis therapy" in system_msg
    assert "### ROLE" in system_msg
    assert "### CONTEXT" in user_msg
    assert "### TASK" in user_msg

    print("Prompt structure test passed!")


def test_smart_fallback_boolean_query_phrase_extraction():
    from webapp.llm import LLMClient

    client = LLMClient()
    client.client = object()
    # Simulate LLM returning empty or invalid string, forcing _fallback_boolean_query
    client.chat_completion_text = lambda *args, **kwargs: ""

    query1 = "What's the relationship between health chatbot and mental health?"
    res1 = client.translate_query_to_boolean(query1)
    assert res1 == '"health chatbot" AND "mental health"'

    query2 = "How does Icariin regulate osteoblast differentiation?“"
    res2 = client.translate_query_to_boolean(query2)
    assert res2 == '"Icariin" AND "osteoblast differentiation"'
    assert "“" not in res2


if __name__ == "__main__":
    test_prompt_structure()
    test_smart_fallback_boolean_query_phrase_extraction()
