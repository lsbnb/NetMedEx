import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from netmedex.rag import AbstractDocument, AbstractRAG
from netmedex.chat import ChatSession


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
        # Test the regex for citation formatting in chat.py if possible
        # Or just test ChatSession message building
        self.rag.get_context = MagicMock(
            return_value=("Remdesivir is effective. [PMID:123456]", ["123456"])
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


if __name__ == "__main__":
    unittest.main()
