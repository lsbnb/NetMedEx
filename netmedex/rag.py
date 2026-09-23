from __future__ import annotations

"""
RAG (Retrieval-Augmented Generation) System for PubMed Abstracts

This module provides a RAG system that indexes PubMed abstracts into a vector database
and enables semantic search for relevant context during chat conversations.
"""

import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Maximum tokens allowed per embedding request (OpenAI limit is 300k; use 250k as buffer)
_MAX_TOKENS_PER_BATCH = 250_000
# ChromaDB hard limit is 5 461 documents per add() call; use 5 000 as a safe buffer
_MAX_DOCS_PER_BATCH = 5_000


def _count_tokens(text: str) -> int:
    """Return an approximate token count for *text* using tiktoken when available.

    Falls back to a simple word-count heuristic (÷0.75) if tiktoken is not
    installed so the function never raises an ImportError at runtime.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Rough heuristic: ~0.75 words per token on average
        return int(len(text.split()) / 0.75) + 1


def _build_token_batches(
    documents_text: list[str],
    metadatas: list[dict],
    ids: list[str],
    max_tokens: int = _MAX_TOKENS_PER_BATCH,
    max_docs: int = _MAX_DOCS_PER_BATCH,
) -> list[tuple[list[str], list[dict], list[str]]]:
    """Split documents into batches respecting both *max_tokens* and *max_docs* limits.

    ChromaDB has a hard per-call limit of 5 461 documents; this function keeps
    each batch under both the token budget and the document-count ceiling.

    Returns a list of (texts, metadatas, ids) tuples ready to be passed to
    ``collection.add()``.
    """
    batches: list[tuple[list[str], list[dict], list[str]]] = []
    cur_texts: list[str] = []
    cur_metas: list[dict] = []
    cur_ids: list[str] = []
    cur_tokens = 0

    for text, meta, doc_id in zip(documents_text, metadatas, ids):
        tokens = _count_tokens(text)
        # Flush when either limit would be exceeded
        if (cur_tokens + tokens > max_tokens or len(cur_texts) >= max_docs) and cur_texts:
            batches.append((cur_texts, cur_metas, cur_ids))
            cur_texts, cur_metas, cur_ids = [], [], []
            cur_tokens = 0
        cur_texts.append(text)
        cur_metas.append(meta)
        cur_ids.append(doc_id)
        cur_tokens += tokens

    if cur_texts:
        batches.append((cur_texts, cur_metas, cur_ids))

    return batches


# --- Sparse (BM25) retrieval arm -------------------------------------------------
# Dense embeddings alone cannot separate biomedical symbols that differ by a digit:
# measured on a real 200-abstract HCV/liver-cancer corpus, a "miR-155" query put only
# 1 of the 10 top hits on an abstract that actually mentions it (a miR-122 review
# ranked 2nd), because the embedding encodes "this is about microRNAs" but not which
# one. BM25 is implemented here rather than pulled in via rank_bm25 so existing
# Docker/pip installs keep working without a new dependency, retrieval stays
# reproducible across environments, and the tokenizer can be biomedical-aware.
_BM25_K1 = 1.5
_BM25_B = 0.75
# Rank-fusion constant. The original RRF paper's 60 was tuned for TREC-scale runs;
# on a NetMedEx-sized corpus (a few hundred abstracts) it flattens the rank curve so
# far that a top-1 hit in one arm barely outscores a mid-ranked one. Measured over 5
# entity queries + 4 conceptual queries on a real 200-abstract corpus: K=60 gave
# entity P@8 0.325, K=10 gave 0.400, with conceptual rankings no more disturbed
# (overlap@8 0.656 vs 0.594).
_RRF_K = 10
# Dense candidate pool floor -- see the comment at its use site in search().
_DENSE_CANDIDATE_FLOOR = 1000
# Sparse-arm weight when the query names a specific identifier (a gene/miRNA/variant
# symbol the corpus knows) rather than asking conceptually. For such queries the
# dense arm is not merely weaker but close to useless -- measured: abstracts that
# are *about* miR-155 sat at dense ranks 8, 73, 106, 117, 131, 135 and 190 of 200,
# while BM25 ranked those same seven 1-7 -- so an unweighted fusion lets the dense
# arm veto a correct sparse result. Applying this weight unconditionally would fix
# entity queries (P@8 0.400 -> 0.750) at the cost of conceptual ones (overlap@8
# 0.656 -> 0.344), so it is applied only when the query actually names one.
_SPARSE_WEIGHT_EXACT = 3.0

_WORD_RE = re.compile(r"[a-z0-9]+")
# miR-155 / miRNA-155 / microRNA-155 / hsa-miR-21-5p all denote the same entity but
# share no token under plain splitting. Emitting one canonical "mir<number>" token
# for every surface form is what lets a query written one way match an abstract
# written another -- the same surface-form mismatch that made the graph side miss
# this entity until node aliases were indexed.
_MIRNA_SURFACE_RE = re.compile(
    r"\b(?:hsa|mmu|rno|ptr)?[-\s]?(?:microrna|mirna|mir)[-\s]?(\d+[a-z]?(?:-[35]p)?)\b"
)


def _tokenize_biomedical(text: str) -> list[str]:
    """Lowercase word tokens, plus a canonical token per miRNA surface form."""
    lowered = (text or "").lower()
    tokens = _WORD_RE.findall(lowered)
    for match in _MIRNA_SURFACE_RE.finditer(lowered):
        tokens.append("mir" + match.group(1).replace("-", ""))
    return tokens


class _BM25Index:
    """Minimal BM25-Okapi over an in-memory corpus (non-negative IDF variant)."""

    def __init__(self, corpus_tokens: list[list[str]]):
        self.doc_count = len(corpus_tokens)
        self.doc_lengths = [len(tokens) for tokens in corpus_tokens]
        total_length = sum(self.doc_lengths)
        self.avg_doc_length = (total_length / self.doc_count) if self.doc_count else 0.0
        # term -> {doc_index: term_frequency}
        self.postings: dict[str, dict[int, int]] = defaultdict(dict)
        for doc_index, tokens in enumerate(corpus_tokens):
            for term, freq in Counter(tokens).items():
                self.postings[term][doc_index] = freq
        self.idf = {
            term: math.log(1 + (self.doc_count - len(docs) + 0.5) / (len(docs) + 0.5))
            for term, docs in self.postings.items()
        }

    def has_exact_identifier(self, query_tokens: list[str]) -> bool:
        """True when a query token looks like a specific biomedical identifier
        (letters and digits together: mir155, tp53, c797s, g12d) and the corpus
        actually contains it. Distinguishes "what does miR-155 do?" from "how do
        microRNAs regulate inflammation?", which need opposite retrieval biases.
        """
        for token in query_tokens:
            if not (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)):
                continue
            if token in self.postings:
                return True
        return False

    def scores(self, query_tokens: list[str]) -> dict[int, float]:
        """Sparse scores keyed by doc index; absent docs scored zero."""
        scores: dict[int, float] = defaultdict(float)
        denom_base = self.avg_doc_length or 1.0
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_index, freq in self.postings[term].items():
                norm = 1 - _BM25_B + _BM25_B * (self.doc_lengths[doc_index] / denom_base)
                scores[doc_index] += idf * (freq * (_BM25_K1 + 1)) / (freq + _BM25_K1 * norm)
        return scores


@dataclass
class AbstractDocument:
    """Represents a PubMed abstract as a RAG document"""

    pmid: str
    title: str
    abstract: str
    entities: list[dict[str, str]]  # Entity metadata from graph
    edges: list[dict[str, Any]]  # Edge information
    weight: float = 1.0  # Citation-based weight


class AbstractRAG:
    """RAG system for indexing and retrieving PubMed abstracts"""

    def __init__(
        self,
        llm_client=None,
        collection_name: str = "abstracts",
        persist_directory: str | None = None,
    ):
        """
        Initialize the RAG system.

        Args:
            llm_client: LLM client with embeddings capability
            collection_name: Name for the vector database collection
            persist_directory: Optional path for persistent storage
        """
        self.llm_client = llm_client
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.documents: dict[str, AbstractDocument] = {}
        # Sparse arm, built alongside the vector index (see index_abstracts).
        # NETMEDEX_DISABLE_BM25=1 restores dense-only retrieval, so the two
        # configurations can be compared with the evaluation harness.
        self.use_bm25 = os.getenv("NETMEDEX_DISABLE_BM25", "").strip() not in ("1", "true", "True")
        self._bm25: _BM25Index | None = None
        self._bm25_pmids: list[str] = []
        self.collection = None
        self._initialized = False

        try:
            import chromadb
            from chromadb.config import Settings

            if self.persist_directory:
                logger.info(f"Using persistent ChromaDB at {self.persist_directory}")
                self.client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(anonymized_telemetry=False, allow_reset=True),
                )
            else:
                # Initialize ChromaDB with ephemeral (in-memory) storage.
                # chromadb.Client(Settings(...)) was removed in chromadb >=1.x;
                # use EphemeralClient() instead.
                self.client = chromadb.EphemeralClient(
                    settings=Settings(anonymized_telemetry=False, allow_reset=True)
                )

            # Standardize to ChromaDB default embeddings for all providers.
            # This avoids provider-specific embedding endpoint compatibility issues.
            self.embedding_fn = None
            logger.info("Using ChromaDB default embeddings")

            logger.info("ChromaDB client initialized")
        except ImportError:
            logger.error("ChromaDB not installed. Please install: pip install chromadb")
            raise

    def index_abstracts(self, abstracts: list[AbstractDocument], progress_callback=None) -> int:
        """
        Index abstracts into the vector database.

        Args:
            abstracts: List of AbstractDocument objects to index
            progress_callback: Optional callback(message) for progress updates

        Returns:
            Number of documents indexed
        """
        if not abstracts:
            logger.warning("No abstracts to index")
            return 0

        logger.info(f"Indexing {len(abstracts)} abstracts into vector store...")
        try:
            # Reset collection if exists
            if self._initialized:
                self.client.reset()

            # Create new collection; hnsw_random_seed fixes HNSW index randomness for reproducibility
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "PubMed abstracts for RAG", "hnsw_random_seed": 42},
                embedding_function=self.embedding_fn,
            )

            # Prepare documents for indexing
            documents_text = []
            metadatas = []
            ids = []

            for doc in abstracts:
                # Combine title and abstract for better context
                full_text = f"{doc.title}\n\n{doc.abstract}"
                documents_text.append(full_text)

                # Store metadata
                metadatas.append(
                    {
                        "pmid": doc.pmid,
                        "title": doc.title,
                        "entity_count": str(len(doc.entities)),
                        "edge_count": str(len(doc.edges)),
                        "weight": str(doc.weight),
                    }
                )

                ids.append(f"pmid_{doc.pmid}")

                # Store full document for retrieval
                self.documents[doc.pmid] = doc

            if progress_callback:
                progress_callback(f"Indexing {len(abstracts)} abstracts...")

            # Split into token-aware batches to respect the 300k tokens/request limit.
            batches = _build_token_batches(documents_text, metadatas, ids)
            total_batches = len(batches)
            logger.info(
                f"Splitting {len(abstracts)} abstracts into {total_batches} batch(es) "
                f"(max {_MAX_TOKENS_PER_BATCH:,} tokens each)"
            )

            try:
                for batch_idx, (batch_texts, batch_metas, batch_ids) in enumerate(
                    batches, start=1
                ):
                    logger.info(
                        f"Sending batch {batch_idx}/{total_batches} "
                        f"({len(batch_texts)} docs) to vector store..."
                    )
                    self.collection.add(
                        documents=batch_texts,
                        metadatas=batch_metas,
                        ids=batch_ids,
                    )
                    if progress_callback:
                        progress_callback(
                            f"Indexed batch {batch_idx}/{total_batches} "
                            f"({len(batch_texts)} abstracts)..."
                        )
            except Exception as e:
                logger.error(f"Exception during collection.add: {e}", exc_info=True)
                raise e

            # Sparse arm over the FULL corpus, not just the dense candidate pool:
            # the documents BM25 exists to rescue are exactly the ones the dense
            # arm ranks too low to retrieve at all.
            if self.use_bm25:
                self._bm25_pmids = [doc.pmid for doc in abstracts]
                self._bm25 = _BM25Index(
                    [_tokenize_biomedical(text) for text in documents_text]
                )
                logger.info(f"Built BM25 sparse index over {len(self._bm25_pmids)} abstracts")
            else:
                self._bm25, self._bm25_pmids = None, []
                logger.info("BM25 sparse arm disabled (NETMEDEX_DISABLE_BM25)")

            self._initialized = True
            logger.info(
                f"Indexed {len(abstracts)} abstracts successfully in {total_batches} batch(es)"
            )

            if progress_callback:
                progress_callback(f"✅ Indexed {len(abstracts)} abstracts")

            return len(abstracts)

        except Exception as e:
            logger.error(f"Error indexing abstracts: {e}", exc_info=True)
            raise

    def search(
        self, query: str, top_k: int = 5, preferred_pmids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """
        Search for relevant abstracts.

        Args:
            query: Search query
            top_k: Number of results to return
            preferred_pmids: Optional set of PMIDs to boost in the search results

        Returns:
            List of (pmid, relevance_score) tuples
        """
        if not self._initialized or self.collection is None:
            logger.warning("RAG system not initialized")
            return []

        try:
            # Query a larger candidate pool to allow preferred PMIDs to be boosted into top_k.
            # The floor also keeps the two retrieval arms over a comparable candidate
            # universe: BM25 scores the whole corpus, so a small dense pool would make
            # "appears in both arms" (worth ~2x under RRF) dominate rank quality, which
            # measurably buried correct BM25 hits. Typical NetMedEx corpora are a few
            # hundred abstracts (max_articles defaults to 200), so this covers them fully.
            candidate_k = min(len(self.documents), max(top_k * 4, _DENSE_CANDIDATE_FLOOR))
            if candidate_k <= 0:
                return []

            results = self.collection.query(query_texts=[query], n_results=candidate_k)

            # --- Dense arm: semantic similarity weighted by citation impact ---
            dense_scores: dict[str, float] = {}
            if results["ids"] and results["distances"]:
                for doc_id, distance in zip(results["ids"][0], results["distances"][0]):
                    pmid = doc_id.replace("pmid_", "")
                    # ChromaDB uses L2 distance, so invert it into a similarity
                    similarity = 1.0 / (1.0 + distance)
                    doc = self.documents.get(pmid)
                    dense_scores[pmid] = similarity * (doc.weight if doc else 1.0)

            if self._bm25 is None:
                # Dense-only: preserve the original scoring exactly.
                pmid_scores = [
                    (pmid, score * (1.5 if preferred_pmids and pmid in preferred_pmids else 1.0))
                    for pmid, score in dense_scores.items()
                ]
                pmid_scores.sort(key=lambda x: (-x[1], x[0]))
                logger.info(f"Found {len(pmid_scores)} relevant abstracts for query (dense-only)")
                return pmid_scores[:top_k]

            # --- Sparse arm: exact biomedical term matching over the whole corpus ---
            query_tokens = _tokenize_biomedical(query)
            sparse_scores: dict[str, float] = {}
            for doc_index, score in self._bm25.scores(query_tokens).items():
                if score > 0:
                    sparse_scores[self._bm25_pmids[doc_index]] = score
            sparse_weight = (
                _SPARSE_WEIGHT_EXACT if self._bm25.has_exact_identifier(query_tokens) else 1.0
            )

            # --- Reciprocal Rank Fusion ---
            # Rank-based fusion avoids having to normalize two incomparable score
            # scales (cosine-derived similarity vs unbounded BM25); a document
            # missing from one arm simply contributes nothing from that arm.
            def _ranks(scores: dict[str, float]) -> dict[str, int]:
                ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
                return {pmid: rank for rank, (pmid, _) in enumerate(ordered, start=1)}

            dense_ranks = _ranks(dense_scores)
            sparse_ranks = _ranks(sparse_scores)

            # A document an arm did not return is ranked just past that arm's tail
            # rather than contributing nothing. Skipping it instead would make mere
            # presence in both arms worth roughly double the best possible
            # single-arm score, regardless of rank: measured on a real corpus, that
            # sank a query whose 7 relevant abstracts BM25 had ranked 1-7 to a single
            # hit in the fused top 8, because mid-ranked documents happened to appear
            # in both arms.
            dense_miss_rank = len(dense_ranks) + 1
            sparse_miss_rank = len(sparse_ranks) + 1

            fused: dict[str, float] = {}
            for pmid in set(dense_ranks) | set(sparse_ranks):
                score = 1.0 / (_RRF_K + dense_ranks.get(pmid, dense_miss_rank))
                score += sparse_weight / (_RRF_K + sparse_ranks.get(pmid, sparse_miss_rank))
                # Graph-path preference still applies, and now also lifts documents
                # that only the sparse arm surfaced.
                if preferred_pmids and pmid in preferred_pmids:
                    score *= 1.5
                fused[pmid] = score

            # Rescale so the top result is 1.0: RRF values are tiny by construction
            # (~0.03) and this score is rendered to the LLM as "Relevance: x.xx".
            # Monotonic, so ordering is untouched.
            best = max(fused.values(), default=0.0) or 1.0
            pmid_scores = [(pmid, score / best) for pmid, score in fused.items()]
            pmid_scores.sort(key=lambda x: (-x[1], x[0]))

            logger.info(
                f"Found {len(pmid_scores)} relevant abstracts for query "
                f"(dense {len(dense_ranks)} + BM25 {len(sparse_ranks)}, RRF-fused)"
            )
            # Slice down to top_k only after re-ranking and boosting
            return pmid_scores[:top_k]

        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

    def search_with_components(
        self, query: str, top_k: int = 5, preferred_pmids: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """Like search(), but returns the raw scoring components instead of just the final
        (pmid, score) tuple, so a caller can recompute the ranking under a different
        preferred_pmid boost multiplier without re-querying ChromaDB.

        Each row carries both retrieval arms' ranks (`dense_rank`/`sparse_rank`, None when
        that arm did not return the document) plus the fusion constants in force, so the
        caller can reproduce search()'s fused score exactly -- calibrating the boost against
        the old `similarity * weight * boost` formula would otherwise be tuning a scoring
        rule the live path no longer uses.

        This is a separate method rather than a parameter on search() so search()'s return
        type and existing call sites are completely unaffected -- added for
        evaluation/calibrate_hybrid_boost.py, not used by the live search()/get_context() path.
        """
        if not self._initialized or self.collection is None:
            logger.warning("RAG system not initialized")
            return []

        candidate_k = min(len(self.documents), max(top_k * 4, _DENSE_CANDIDATE_FLOOR))
        if candidate_k <= 0:
            return []

        results = self.collection.query(query_texts=[query], n_results=candidate_k)

        dense_raw: dict[str, tuple[float, float]] = {}
        if results["ids"] and results["distances"]:
            for doc_id, distance in zip(results["ids"][0], results["distances"][0]):
                pmid = doc_id.replace("pmid_", "")
                similarity = 1.0 / (1.0 + distance)
                doc = self.documents.get(pmid)
                dense_raw[pmid] = (similarity, doc.weight if doc else 1.0)

        sparse_raw: dict[str, float] = {}
        sparse_weight = 1.0
        if self._bm25 is not None:
            query_tokens = _tokenize_biomedical(query)
            for doc_index, score in self._bm25.scores(query_tokens).items():
                if score > 0:
                    sparse_raw[self._bm25_pmids[doc_index]] = score
            if self._bm25.has_exact_identifier(query_tokens):
                sparse_weight = _SPARSE_WEIGHT_EXACT

        def _ranks(scores: dict[str, float]) -> dict[str, int]:
            ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            return {pmid: rank for rank, (pmid, _) in enumerate(ordered, start=1)}

        dense_ranks = _ranks({pmid: sim * w for pmid, (sim, w) in dense_raw.items()})
        sparse_ranks = _ranks(sparse_raw)

        components: list[dict[str, Any]] = []
        for pmid in set(dense_ranks) | set(sparse_ranks):
            similarity, weight = dense_raw.get(pmid, (0.0, 1.0))
            components.append(
                {
                    "pmid": pmid,
                    "similarity": similarity,
                    "weight": weight,
                    "is_preferred": bool(preferred_pmids and pmid in preferred_pmids),
                    "dense_rank": dense_ranks.get(pmid),
                    "sparse_rank": sparse_ranks.get(pmid),
                    "dense_arm_size": len(dense_ranks),
                    "sparse_arm_size": len(sparse_ranks),
                    "sparse_weight": sparse_weight,
                    "rrf_k": _RRF_K,
                }
            )
        return components

    def get_context(
        self, query: str, top_k: int = 5, preferred_pmids: set[str] | None = None
    ) -> tuple[str, list[str]]:
        """
        Get formatted context for LLM prompt.

        Args:
            query: User query
            top_k: Number of abstracts to retrieve
            preferred_pmids: Optional set of PMIDs to boost in retrieval

        Returns:
            Tuple of (formatted_context, list of PMIDs used)
        """
        results = self.search(query, top_k=top_k, preferred_pmids=preferred_pmids)

        if not results:
            return "No relevant abstracts found.", []

        context_parts = []
        pmids_used = []

        for pmid, score in results:
            if pmid in self.documents:
                doc = self.documents[pmid]
                part = [
                    f"PMID: {pmid} (Relevance: {score:.2f})",
                    f"Title: {doc.title}",
                    f"Abstract: {doc.abstract}",
                ]

                # Include structured semantic relationships if available
                if doc.edges:
                    # De-duplicate relationships for the prompt (sometimes multiple PMIDs map to same edge)
                    unique_rels = set()
                    for edge in doc.edges:
                        source = edge.get("source", "Unknown")
                        target = edge.get("target", "Unknown")
                        # relations is a list of strings
                        rels = edge.get("relations", ["associated"])
                        for r in rels:
                            unique_rels.add(f"- {source} --[{r}]--> {target}")

                    if unique_rels:
                        part.append("Structural Relationships (Extracted):")
                        # Limit to top 15 edges to avoid context window pressure
                        part.extend(sorted(list(unique_rels))[:15])

                context_parts.append("\n".join(part))
                pmids_used.append(pmid)

        context = "\n---\n\n".join(context_parts)
        return context, pmids_used

    def get_document(self, pmid: str) -> AbstractDocument | None:
        """Get a specific document by PMID"""
        return self.documents.get(pmid)

    def get_all_pmids(self) -> list[str]:
        """Get list of all indexed PMIDs"""
        return list(self.documents.keys())

    def clear(self):
        """Clear the RAG system"""
        if self.client:
            self.client.reset()
        self.documents.clear()
        self.collection = None
        self._initialized = False
        logger.info("RAG system cleared")
