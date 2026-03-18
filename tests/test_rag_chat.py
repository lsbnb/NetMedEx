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
        with patch("chromadb.Client") as mock_chroma:
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
        self.rag.documents["123456"] = AbstractDocument(
            pmid="123456",
            title="Test Document",
            abstract="Test Abstract",
            entities=[],
            edges=[],
        )

        session = ChatSession(self.rag, self.llm_client)

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Remdesivir is effective [PMID:123456]."
        self.llm_client.client.chat.completions.create.return_value = mock_response

        result = session.send_message("Is Remdesivir effective?")

        self.assertTrue(result["success"])
        self.assertIn("123456", result["sources"])

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


if __name__ == "__main__":
    unittest.main()
