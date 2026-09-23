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

    def test_followup_turn_boosts_previous_citations_without_restricting_the_index(self):
        """A follow-up question must still search the FULL index every turn -- the
        previous reply's cited PMIDs are folded into preferred_pmids as a ranking
        boost (so a still-relevant PMID can resurface) alongside whatever this
        turn's own retrieval finds, never as a restriction to only those PMIDs.
        Hard-restricting scope is a separate, opt-in mode (strict_pmid_grounding)."""
        self.rag.documents["1234567"] = AbstractDocument(
            pmid="1234567", title="Doc A", abstract="Abstract A", entities=[], edges=[]
        )
        self.rag.documents["7654321"] = AbstractDocument(
            pmid="7654321", title="Doc B", abstract="Abstract B", entities=[], edges=[]
        )
        self.rag._initialized = True
        self.rag.search = MagicMock(return_value=[("1234567", 1.0)])

        session = ChatSession(self.rag, self.llm_client)

        first_response = MagicMock()
        first_response.choices = [MagicMock()]
        first_response.choices[0].message.content = "First answer [PMID:1234567]."
        self.llm_client.client.chat.completions.create.return_value = first_response
        result1 = session.send_message("First question?")
        self.assertTrue(result1["success"])
        self.assertIn("1234567", result1["sources"])

        second_response = MagicMock()
        second_response.choices = [MagicMock()]
        second_response.choices[0].message.content = "Second answer [PMID:7654321]."
        self.llm_client.client.chat.completions.create.return_value = second_response
        result2 = session.send_message("Follow-up question?")
        self.assertTrue(result2["success"])

        # The follow-up turn's search call was seeded with the prior reply's
        # citation as a boost (no graph_retriever is configured in this test, so
        # this can only have come from _last_cited_pmids(), not fresh graph paths).
        self.assertIn("1234567", self.rag.search.call_args.kwargs["preferred_pmids"])

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

    def test_entity_listing_query_recognizes_which_x_are_related_phrasing(self):
        """'哪一些miRNA與X有關' / 'Which miRNAs are related to X' name the entity
        between the trigger words ('哪一些...有關', 'which...are'), not adjacent
        to them like the original 'list'/'which are' triggers expected -- live
        found via a real HCV/liver-cancer query that fell through to the normal
        LLM reasoning path instead of the deterministic listing path."""
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

        for question in (
            "哪一些miRNA與HCV引發的肝癌有關",
            "Which miRNAs are associated with HCV-induced liver cancer?",
        ):
            result = session.send_message(question)
            self.assertTrue(result["success"])
            self.assertIn("miR-1", result["message"])
            self.assertNotIn("TP53", result["message"])
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

    def test_suggest_semantic_edge_method_when_cooccurrence_graph_lacks_directional_edges(self):
        from netmedex.graph_rag import GraphRetriever

        graph = nx.Graph()
        graph.add_node("A", name="GeneA", type="Gene", pmids={"1"})
        graph.add_node("B", name="GeneB", type="Gene", pmids={"1"})
        graph.add_edge("A", "B", edge_weight=1.0)
        graph.graph["edge_method"] = "co-occurrence"

        session = ChatSession(
            self.rag, self.llm_client, graph_retriever=GraphRetriever(graph)
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "GeneA and GeneB are co-mentioned."
        self.llm_client.client.chat.completions.create.return_value = mock_response

        result = session.send_message("How does GeneA affect GeneB?", focus_nodes=["A", "B"])

        self.assertTrue(result["success"])
        self.assertTrue(result["suggest_semantic_edge_method"])

    def test_no_suggestion_when_graph_already_built_with_semantic_edge_method(self):
        """Even with no directional edges *this specific turn*, switching edge method
        again would not help if the graph was already built with edge_method=semantic --
        the nudge must not fire in that case."""
        from netmedex.graph_rag import GraphRetriever

        graph = nx.Graph()
        graph.add_node("A", name="GeneA", type="Gene", pmids={"1"})
        graph.add_node("B", name="GeneB", type="Gene", pmids={"1"})
        graph.add_edge("A", "B", edge_weight=1.0)
        graph.graph["edge_method"] = "semantic"

        session = ChatSession(
            self.rag, self.llm_client, graph_retriever=GraphRetriever(graph)
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "GeneA and GeneB are co-mentioned."
        self.llm_client.client.chat.completions.create.return_value = mock_response

        result = session.send_message("How does GeneA affect GeneB?", focus_nodes=["A", "B"])

        self.assertTrue(result["success"])
        self.assertFalse(result["suggest_semantic_edge_method"])


class TestTranslationDegradedVisibility(unittest.TestCase):
    """The English Intermediary (send_message's pre-retrieval translation step)
    must surface it when a CJK/non-English query silently ran through retrieval
    untranslated, instead of only logging it -- see webapp/llm.py's
    last_translation_status and chat.py's translation_degraded flag."""

    def setUp(self):
        self.llm_client = MagicMock()
        self.llm_client.api_key = "test-key"
        self.llm_client.base_url = None
        self.llm_client.model = "gpt-4o-mini"
        self.llm_client.client = MagicMock()
        # A plain MagicMock auto-vivifies last_translation_status as another
        # MagicMock, which chat.py's `!= "ok"` check would misread as degraded --
        # pin it to the real LLMClient's default so only the scenario each test
        # sets up (or doesn't) determines the outcome.
        self.llm_client.last_translation_status = "ok"

        with patch("chromadb.EphemeralClient") as mock_chroma:
            mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
            self.rag = AbstractRAG(self.llm_client)

        self.rag.documents["1234567"] = AbstractDocument(
            pmid="1234567", title="Test Document", abstract="Test Abstract",
            entities=[], edges=[],
        )
        self.rag._initialized = True
        self.rag.search = MagicMock(return_value=[("1234567", 1.0)])

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Answer [PMID:1234567]."
        self.llm_client.client.chat.completions.create.return_value = mock_response

    def test_flag_set_when_llm_lacks_translate_to_english(self):
        """chat.py already logs a warning for this (line ~1239); it must now also
        flag the turn so the caller/UI can tell the user, not just the logs."""
        del self.llm_client.translate_to_english  # hasattr(...) must be False
        session = ChatSession(self.rag, self.llm_client)

        result = session.send_message("瑞德西韋對covid有效嗎？")

        self.assertTrue(result["success"])
        self.assertTrue(result["translation_degraded"])

    def test_flag_set_when_translation_call_reports_unavailable(self):
        """translate_to_english exists and runs, but LLMClient.last_translation_status
        says it degraded to the untranslated text (no client configured, etc.)."""

        def fake_translate(text):
            self.llm_client.last_translation_status = "unavailable"
            return text

        self.llm_client.translate_to_english = MagicMock(side_effect=fake_translate)
        session = ChatSession(self.rag, self.llm_client)

        result = session.send_message("瑞德西韋對covid有效嗎？")

        self.assertTrue(result["success"])
        self.assertTrue(result["translation_degraded"])

    def test_flag_not_set_on_successful_translation(self):
        """The ordinary, working case: translate_to_english runs and reports "ok" --
        must not be mistaken for a degraded fallback."""
        self.llm_client.translate_to_english = MagicMock(
            return_value="Is remdesivir effective against covid?"
        )
        self.llm_client.last_translation_status = "ok"
        session = ChatSession(self.rag, self.llm_client)

        result = session.send_message("瑞德西韋對covid有效嗎？")

        self.assertTrue(result["success"])
        self.assertFalse(result["translation_degraded"])

    def test_flag_not_set_when_translation_not_needed(self):
        """An English query in an English session never enters the translation
        branch at all, so the flag must default to False, not be left unset."""
        session = ChatSession(self.rag, self.llm_client)

        result = session.send_message(
            "Is remdesivir effective?", session_language="English"
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["translation_degraded"])


class TestStrictPmidGrounding(unittest.TestCase):
    """v1.6 two-tier 'core evidence circle, then index-wide fallback' follow-up
    retrieval policy (ChatSession._answer_with_pmid_grounding)."""

    def setUp(self):
        self.llm_client = MagicMock()
        self.llm_client.api_key = "test-key"
        self.llm_client.base_url = None
        self.llm_client.model = "gpt-4o-mini"
        self.llm_client.client = MagicMock()
        # Force the SDK-fallback path (chat_completion_text returns a non-string
        # MagicMock by default, which _call_llm_for_chat_completion already
        # detects and falls back from -- matching how the rest of this file
        # mocks LLM responses via client.chat.completions.create).

        with patch("chromadb.EphemeralClient") as mock_chroma:
            self.mock_collection = MagicMock()
            mock_chroma.return_value.get_or_create_collection.return_value = self.mock_collection
            self.rag = AbstractRAG(self.llm_client)

    @staticmethod
    def _text_response(content: str) -> MagicMock:
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response

    def _seed_previous_reply(self, session: ChatSession, pmids: list[str]) -> None:
        """Simulate a completed prior turn citing `pmids`, as _last_cited_pmids reads."""
        from netmedex.chat import ChatMessage

        session.history.append(ChatMessage(role="user", content="initial question"))
        session.history.append(
            ChatMessage(role="assistant", content="initial answer", sources=pmids)
        )

    def test_first_turn_has_no_previous_pmids_and_uses_normal_flow(self):
        """With no prior reply to ground on, strict_pmid_grounding must have no
        effect -- the normal single-tier flow runs exactly once."""
        session = ChatSession(self.rag, self.llm_client)
        self.llm_client.client.chat.completions.create.return_value = self._text_response(
            "A general answer with no citations."
        )

        result = session.send_message("What is resveratrol?", strict_pmid_grounding=True)

        self.assertTrue(result["success"])
        self.assertEqual(self.llm_client.client.chat.completions.create.call_count, 1)

    def test_tier1_answers_from_previous_pmids_alone_without_reaching_tier2(self):
        self.rag.documents["1234567"] = AbstractDocument(
            pmid="1234567",
            title="Remdesivir Study",
            abstract="Remdesivir inhibits SARS-CoV-2 replication in cell cultures.",
            entities=[],
            edges=[],
        )
        session = ChatSession(self.rag, self.llm_client)
        self._seed_previous_reply(session, ["1234567"])

        self.llm_client.client.chat.completions.create.return_value = self._text_response(
            "Remdesivir works by inhibiting viral replication [PMID:1234567]."
        )

        result = session.send_message(
            "How does it work mechanistically?", strict_pmid_grounding=True
        )

        self.assertTrue(result["success"])
        self.assertIn("1234567", result["sources"])
        self.assertEqual(self.llm_client.client.chat.completions.create.call_count, 1)

    def test_tier1_sentinel_falls_back_to_tier2_with_disclosure(self):
        self.rag.documents["1234567"] = AbstractDocument(
            pmid="1234567",
            title="Remdesivir Study",
            abstract="Remdesivir inhibits SARS-CoV-2 replication in cell cultures.",
            entities=[],
            edges=[],
        )
        self.rag.documents["7890128"] = AbstractDocument(
            pmid="7890128",
            title="Dexamethasone Study",
            abstract="Dexamethasone reduced mortality in hospitalized COVID-19 patients.",
            entities=[],
            edges=[],
        )
        self.rag._initialized = True
        self.rag.search = MagicMock(return_value=[("7890128", 1.0)])
        session = ChatSession(self.rag, self.llm_client)
        self._seed_previous_reply(session, ["1234567"])

        self.llm_client.client.chat.completions.create.side_effect = [
            self._text_response(session._PMID_GROUNDING_SENTINEL),
            self._text_response("Dexamethasone reduces mortality [PMID:7890128]."),
        ]

        result = session.send_message(
            "What about steroids for COVID-19?", strict_pmid_grounding=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.llm_client.client.chat.completions.create.call_count, 2)
        self.assertIn("7890128", result["message"])
        self.assertIn("7890128", result["message"].split("---")[-1])  # disclosure names it
        self.assertIn("PMID: 7890128", result["message"])

    def test_both_tiers_empty_returns_fixed_refusal_without_any_llm_call(self):
        session = ChatSession(self.rag, self.llm_client)
        # Previous reply cited a PMID that was never actually indexed.
        self._seed_previous_reply(session, ["9999990"])

        result = session.send_message("Anything about gene X?", strict_pmid_grounding=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], session._PMID_GROUNDING_REFUSAL)
        self.assertFalse(self.llm_client.client.chat.completions.create.called)

    def test_restricted_subgraph_excludes_pmid_mismatched_neighbor(self):
        """A -[PMID 1]- B -[PMID 2]- C: restricting to {'1'} must keep A and B
        (and the A-B edge) but must NOT pull in C, even though C is a direct
        neighbor of B -- hopping onto an attribute-mismatched neighbor is exactly
        what the core-evidence-circle design forbids."""
        graph = nx.Graph()
        graph.add_node("A", name="A", type="gene")
        graph.add_node("B", name="B", type="gene")
        graph.add_node("C", name="C", type="gene")
        graph.add_edge("A", "B", relations={"1": {"associated_with"}})
        graph.add_edge("B", "C", relations={"2": {"associated_with"}})

        restricted = ChatSession._build_pmid_restricted_subgraph(graph, {"1"})

        self.assertEqual(set(restricted.nodes()), {"A", "B"})
        self.assertTrue(restricted.has_edge("A", "B"))
        self.assertNotIn("C", restricted.nodes())

    def test_restricted_subgraph_trims_non_restricted_pmid_out_of_shared_edge(self):
        """An edge co-cited by both a restricted PMID ('1') and a non-restricted
        one ('2') must keep only PMID 1's relation/evidence/confidence -- an
        any-match keep/discard gate alone would let PMID 2's own data ride along
        inside the "restricted" edge and risk being selected and cited by
        _select_edge_support, defeating the grounding guarantee entirely."""
        graph = nx.Graph()
        graph.add_node("A", name="A", type="gene")
        graph.add_node("B", name="B", type="gene")
        graph.add_edge(
            "A",
            "B",
            relations={"1": {"promotes"}, "2": {"inhibits"}},
            evidences={
                "1": {"promotes": "A promotes B per study 1."},
                "2": {"inhibits": "A inhibits B per study 2."},
            },
            confidences={"1": {"promotes": 0.6}, "2": {"inhibits": 0.95}},
        )

        restricted = ChatSession._build_pmid_restricted_subgraph(graph, {"1"})
        edge_data = restricted.edges["A", "B"]

        self.assertEqual(set(edge_data["relations"]), {"1"})
        self.assertEqual(set(edge_data["evidences"]), {"1"})
        self.assertEqual(set(edge_data["confidences"]), {"1"})


class TestSparseRetrievalArm(unittest.TestCase):
    """BM25 sparse arm and hybrid rank fusion (netmedex/rag.py).

    Added after measuring that dense-only retrieval could not answer exact-entity
    questions on a real 200-abstract corpus: a "miR-155" query returned 1 of the 7
    abstracts that discuss it (a miR-122 review outranked them), because the
    embedding encodes "this is about microRNAs" but not which one.
    """

    def _index(self):
        from netmedex.rag import _BM25Index, _tokenize_biomedical

        corpus = [
            "miR-155 is a pro-inflammatory mediator in liver cancer",
            "miRNA-155 upregulation in HCV-related hepatocellular carcinoma",
            "microRNA-122 is the most abundant liver microRNA",
            "A general review of microRNA biology and cancer",
        ]
        return _BM25Index([_tokenize_biomedical(doc) for doc in corpus])

    def test_tokenizer_canonicalizes_mirna_surface_variants(self):
        """miR-155 / miRNA-155 / microRNA-155 name the same entity but share no
        token under plain splitting -- the exact mismatch that made a "miR-155"
        question miss abstracts written as "miRNA-155"."""
        from netmedex.rag import _tokenize_biomedical

        for surface in ("miR-155", "miRNA-155", "microRNA-155", "MiR 155", "hsa-miR-155"):
            self.assertIn("mir155", _tokenize_biomedical(surface), surface)

    def test_tokenizer_keeps_distinct_mirnas_distinct(self):
        from netmedex.rag import _tokenize_biomedical

        tokens = _tokenize_biomedical("miR-129 versus miR-1290")
        self.assertIn("mir129", tokens)
        self.assertIn("mir1290", tokens)

    def test_tokenizer_preserves_strand_suffix(self):
        from netmedex.rag import _tokenize_biomedical

        self.assertIn("mir215p", _tokenize_biomedical("hsa-miR-21-5p expression"))

    def test_tokenizer_does_not_invent_mirna_tokens_from_ordinary_words(self):
        from netmedex.rag import _tokenize_biomedical

        tokens = _tokenize_biomedical("mirror image of the miracle drug")
        self.assertFalse([t for t in tokens if t.startswith("mir") and any(c.isdigit() for c in t)])

    def test_bm25_ranks_exact_entity_match_above_generic_review(self):
        from netmedex.rag import _tokenize_biomedical

        index = self._index()
        scores = index.scores(_tokenize_biomedical("What does miR-155 do?"))
        # Docs 0 and 1 name the entity (in two surface forms); 2 and 3 do not.
        self.assertGreater(scores.get(0, 0), scores.get(3, 0))
        self.assertGreater(scores.get(1, 0), scores.get(3, 0))

    def test_bm25_matches_across_surface_form_variants(self):
        """Querying "miR-155" must reach the abstract that writes "miRNA-155"."""
        from netmedex.rag import _tokenize_biomedical

        index = self._index()
        self.assertGreater(index.scores(_tokenize_biomedical("miR-155")).get(1, 0), 0)

    def test_unknown_identifier_contributes_no_exact_match_signal(self):
        """A miRNA the corpus never mentions has no canonical token to match on.
        Generic tokens ("mir") still overlap, which is ordinary BM25 behaviour --
        what must not happen is an absent identifier scoring like a present one."""
        from netmedex.rag import _tokenize_biomedical

        index = self._index()
        self.assertNotIn("mir9999", index.postings)
        known = max(index.scores(_tokenize_biomedical("miR-155")).values())
        unknown = max(index.scores(_tokenize_biomedical("miR-9999")).values(), default=0.0)
        self.assertGreater(known, unknown)

    def test_exact_identifier_detection_separates_named_entity_from_concept(self):
        """Drives the adaptive sparse weighting: the dense arm is near-useless for
        the first kind of query and appropriate for the second."""
        from netmedex.rag import _tokenize_biomedical

        index = self._index()
        named = _tokenize_biomedical("What is the role of miR-155 in liver cancer?")
        concept = _tokenize_biomedical("How does chronic inflammation drive liver cancer?")
        self.assertTrue(index.has_exact_identifier(named))
        self.assertFalse(index.has_exact_identifier(concept))

    def test_exact_identifier_detection_ignores_symbols_absent_from_corpus(self):
        from netmedex.rag import _tokenize_biomedical

        index = self._index()
        self.assertFalse(index.has_exact_identifier(_tokenize_biomedical("role of miR-4999")))


if __name__ == "__main__":
    unittest.main()
