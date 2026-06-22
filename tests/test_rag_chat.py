import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import networkx as nx

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from netmedex.chat import ChatSession
from netmedex.rag import AbstractDocument, AbstractRAG


class TestRAGChat(unittest.TestCase):
    def setUp(self):
        self.llm_client = MagicMock()
        self.llm_client.api_key = "test-key"
        self.llm_client.base_url = None
        self.llm_client.model = "gpt-4o-mini"
        self.llm_client.client = MagicMock()

        # Mock ChromaDB
        with patch("chromadb.EphemeralClient") as mock_chroma:
            self.mock_collection = MagicMock()
            mock_chroma.return_value.get_or_create_collection.return_value = self.mock_collection
            self.rag = AbstractRAG(self.llm_client)

        # Sample documents
        self.docs = [
            AbstractDocument(
                pmid="123456",
                title="COVID-19 and Remdesivir",
                abstract="Remdesivir inhibits SARS-CoV-2 replication in cell cultures.",
                entities=["Remdesivir", "SARS-CoV-2"],
                edges=[],
            ),
            AbstractDocument(
                pmid="789012",
                title="Dexamethasone and COVID-19",
                abstract="Dexamethasone reduced mortality in hospitalized COVID-19 patients.",
                entities=["Dexamethasone", "COVID-19"],
                edges=[],
            ),
        ]

    def test_rag_indexing(self):
        # Use the RAG with mocked collection
        self.rag.index_abstracts(self.docs)

        # Verify collection.add was called
        self.assertTrue(self.mock_collection.add.called)

    def test_citation_formatting(self):
        # Populate rag.documents because ChatSession optimization uses all docs if count <= 20
        # effectively bypassing get_context()
        self.rag.documents["1234567"] = AbstractDocument(
            pmid="1234567",
            title="Test Document",
            abstract="Test Abstract",
            entities=[],
            edges=[],
        )
        self.rag._initialized = True
        self.rag.search = MagicMock(return_value=[("1234567", 1.0)])

        session = ChatSession(self.rag, self.llm_client)

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Remdesivir is effective [PMID:1234567]."
        self.llm_client.client.chat.completions.create.return_value = mock_response

        result = session.send_message("Is Remdesivir effective?")

        self.assertTrue(result["success"])
        self.assertIn("1234567", result["sources"])

    def test_entity_listing_query_returns_full_mirna_list_from_graph(self):
        graph = nx.Graph()
        for i in range(1, 7):
            graph.add_node(
                f"mir-{i}",
                name=f"miR-{i}",
                type="Gene",
                pmids={str(100000 + i)},
            )
        graph.add_node("gene-a", name="TP53", type="Gene", pmids={"200001"})

        graph_retriever = MagicMock()
        graph_retriever.graph = graph

        session = ChatSession(self.rag, self.llm_client, graph_retriever=graph_retriever)
        result = session.send_message("請列出所有 miRNA")

        self.assertTrue(result["success"])
        self.assertIn("miR-1", result["message"])
        self.assertIn("miR-6", result["message"])
        self.assertNotIn("TP53", result["message"])
        # Deterministic listing path should bypass LLM chat completion.
        self.assertFalse(self.llm_client.client.chat.completions.create.called)

    def test_history_save_and_load(self):
        import tempfile
        import os
        from netmedex.chat import ChatMessage

        session = ChatSession(self.rag, self.llm_client)
        session.history = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there", full_content="Hi there full"),
        ]
        session.full_history = list(session.history)
        session.memory_buffer = ["Turn 1 Q & A summary"]

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "chat_history.json")
            session.save_to_file(filepath)

            # Recreate session and load
            new_session = ChatSession(self.rag, self.llm_client)
            success = new_session.load_from_file(filepath)
            
            self.assertTrue(success)
            self.assertEqual(len(new_session.history), 2)
            self.assertEqual(new_session.history[0].content, "Hello")
            self.assertEqual(new_session.history[1].full_content, "Hi there full")
            self.assertEqual(len(new_session.full_history), 2)
            self.assertEqual(new_session.full_history[1].full_content, "Hi there full")
            self.assertEqual(new_session.memory_buffer, ["Turn 1 Q & A summary"])

    def test_entity_listing_added_to_full_history(self):
        graph = nx.Graph()
        graph.add_node("mir-1", name="miR-1", type="Gene", pmids={"100001"})
        graph_retriever = MagicMock()
        graph_retriever.graph = graph

        session = ChatSession(self.rag, self.llm_client, graph_retriever=graph_retriever)
        result = session.send_message("請列出所有 miRNA")

        self.assertTrue(result["success"])
        # Check that both history and full_history are populated
        self.assertEqual(len(session.history), 2)
        self.assertEqual(len(session.full_history), 2)
        self.assertEqual(session.full_history[0].content, "請列出所有 miRNA")
        self.assertIn("miR-1", session.full_history[1].content)


if __name__ == "__main__":
    unittest.main()
