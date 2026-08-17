import unittest
from unittest.mock import MagicMock, patch
from netmedex.rag import AbstractRAG, AbstractDocument
from netmedex.chat import ChatSession

class TestGraphBoostedRAG(unittest.TestCase):
    def setUp(self):
        self.llm_client = MagicMock()
        self.llm_client.api_key = "test-key"
        self.llm_client.base_url = None
        self.llm_client.model = "gpt-4o-mini"
        self.llm_client.client = MagicMock()

    def test_rag_search_with_preferred_pmids_boosts_scores(self):
        # Mock ChromaDB Client & Collection
        with patch("chromadb.Client") as mock_chroma:
            mock_collection = MagicMock()
            mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
            
            # Mock collection query return value
            # Standard return format: {"ids": [["pmid_1", "pmid_2"]], "distances": [[0.5, 0.5]]}
            mock_collection.query.return_value = {
                "ids": [["pmid_1", "pmid_2"]],
                "distances": [[0.5, 0.5]]
            }

            rag = AbstractRAG(self.llm_client)
            rag._initialized = True
            rag.collection = mock_collection

            # Mock document registry
            doc1 = AbstractDocument(pmid="1", title="Doc 1", abstract="Abstract 1", entities=[], edges=[], weight=1.0)
            doc2 = AbstractDocument(pmid="2", title="Doc 2", abstract="Abstract 2", entities=[], edges=[], weight=1.0)
            rag.documents = {"1": doc1, "2": doc2}

            # Search WITHOUT preferred PMIDs (should return equal scores since distance & weights are identical)
            results_no_boost = rag.search("test query", top_k=2)
            self.assertEqual(len(results_no_boost), 2)
            self.assertEqual(results_no_boost[0][1], results_no_boost[1][1])

            # Search WITH preferred PMID "2" (should boost score of pmid "2" to be higher and rank first)
            results_with_boost = rag.search("test query", top_k=2, preferred_pmids={"2"})
            self.assertEqual(len(results_with_boost), 2)
            self.assertEqual(results_with_boost[0][0], "2")  # "2" is now ranked first due to boost
            self.assertGreater(results_with_boost[0][1], results_with_boost[1][1])  # score of "2" is greater than "1"

    def test_search_with_components_exposes_raw_scoring_factors(self):
        with patch("chromadb.Client") as mock_chroma:
            mock_collection = MagicMock()
            mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
            mock_collection.query.return_value = {
                "ids": [["pmid_1", "pmid_2"]],
                "distances": [[0.5, 1.0]],
            }

            rag = AbstractRAG(self.llm_client)
            rag._initialized = True
            rag.collection = mock_collection
            doc1 = AbstractDocument(pmid="1", title="Doc 1", abstract="A1", entities=[], edges=[], weight=2.0)
            doc2 = AbstractDocument(pmid="2", title="Doc 2", abstract="A2", entities=[], edges=[], weight=1.0)
            rag.documents = {"1": doc1, "2": doc2}

            components = rag.search_with_components("test query", top_k=2, preferred_pmids={"2"})

            by_pmid = {c["pmid"]: c for c in components}
            self.assertAlmostEqual(by_pmid["1"]["similarity"], 1.0 / 1.5)
            self.assertEqual(by_pmid["1"]["weight"], 2.0)
            self.assertFalse(by_pmid["1"]["is_preferred"])
            self.assertAlmostEqual(by_pmid["2"]["similarity"], 1.0 / 2.0)
            self.assertEqual(by_pmid["2"]["weight"], 1.0)
            self.assertTrue(by_pmid["2"]["is_preferred"])

            # Recomputing hybrid_score from the raw components at boost=1.5 must reproduce
            # search()'s own output exactly -- that's the whole point of this method.
            official = dict(rag.search("test query", top_k=2, preferred_pmids={"2"}))
            for pmid, c in by_pmid.items():
                recomputed = c["similarity"] * c["weight"] * (1.5 if c["is_preferred"] else 1.0)
                self.assertAlmostEqual(recomputed, official[pmid])

    def test_chat_session_extracts_preferred_pmids_and_retrieves(self):
        # Mock RAG system
        rag = MagicMock()
        doc1 = AbstractDocument(pmid="1", title="Title 1", abstract="Abstract 1", entities=[], edges=[], weight=1.0)
        doc2 = AbstractDocument(pmid="2", title="Title 2", abstract="Abstract 2", entities=[], edges=[], weight=1.0)
        doc3 = AbstractDocument(pmid="3", title="Title 3", abstract="Abstract 3", entities=[], edges=[], weight=1.0)
        rag.documents = {"1": doc1, "2": doc2, "3": doc3}
        rag.get_context.return_value = ("Formatted context", ["1", "2"])

        # Mock GraphRetriever
        graph_retriever = MagicMock()
        graph_retriever.find_relevant_nodes.return_value = ["node_A"]
        # get_subgraph_context_with_paths returns (text_context, structured_paths)
        graph_retriever.get_subgraph_context_with_paths.return_value = (
            "Graph paths text",
            [
                {
                    "path": ["node_A", "node_B"],
                    "names": ["A", "B"],
                    "relations": ["associated"],
                    "edge_pmids": [["2", "3"]],
                    "score": 0.9,
                    "hop_count": 1
                }
            ]
        )

        session = ChatSession(rag, self.llm_client, graph_retriever=graph_retriever)
        
        # Mock LLM chat completion
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response from LLM [PMID:2]."
        self.llm_client.client.chat.completions.create.return_value = mock_response

        # Execute send_message
        result = session.send_message("query test")
        
        self.assertTrue(result["success"])
        # Verify get_subgraph_context_with_paths was called first
        graph_retriever.get_subgraph_context_with_paths.assert_called_once()
        
        # Verify get_context was called with the extracted preferred_pmids {"2", "3"}
        rag.get_context.assert_called_once_with(
            "query test",
            top_k=8,
            preferred_pmids={"2", "3"}
        )

if __name__ == "__main__":
    unittest.main()
