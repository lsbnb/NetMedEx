from __future__ import annotations

"""
Semantic Relationship Extraction using LLM

This module provides LLM-based semantic analysis for extracting meaningful
relationships between biomedical entities, as an alternative to simple
co-occurrence-based edge construction.
"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from netmedex.pubtator_data import PubTatorArticle
from netmedex.pubtator_graph_data import PubTatorNode, PubTatorEdge
from netmedex.relation_types import (
    DIRECTIONAL_RELATIONS,
    SYMMETRIC_RELATIONS,
    normalize_relation_type,
)

logger = logging.getLogger(__name__)


@dataclass
class SemanticEdge:
    """Represents a semantically-analyzed relationship between entities"""

    node1_id: str
    node2_id: str
    pmid: str
    relation_type: str
    confidence: float  # 0-1 score from LLM
    evidence: str  # Supporting sentence/phrase from abstract


class SemanticRelationshipExtractor:
    """Extract relationships using LLM semantic analysis"""

    def __init__(self, llm_client, confidence_threshold: float = 0.5, progress_callback=None):
        """
        Initialize the semantic relationship extractor.

        Args:
            llm_client: LLM client instance (e.g., from webapp.llm)
            confidence_threshold: Minimum confidence score to accept edges (0-1)
            progress_callback: Optional callback function(current, total, message) for progress updates
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold
        self.progress_callback = progress_callback
        self.cache: dict[str, list[SemanticEdge]] = {}  # Cache results by PMID
        self.last_article_errors: dict[str, str] = {}
        self._stats_lock = threading.RLock()
        self.last_run_stats: dict[str, Any] = {
            "total_articles": 0,
            "processed_articles": 0,
            "succeeded_articles": 0,
            "failed_articles": 0,
            "api_errors": 0,
            "parse_failures": 0,
            "relaxed_recoveries": 0,
            "compact_retries": 0,
            "coverage_passes": 0,
            "coverage_expansions": 0,
            "dropped_by_threshold": 0,
            "dropped_invalid_nodes": 0,
            "provider": "unknown",
            "model": "unknown",
        }

    def _get_provider(self) -> str:
        """Centralized helper for robust provider detection."""
        if not self.llm_client:
            return "unknown"
        provider = str(getattr(self.llm_client, "provider", "unknown")).lower()
        base_url = str(getattr(self.llm_client, "base_url", "unknown")).lower()

        if (
            provider == "local"
            or "127.0.0.1" in base_url
            or "localhost" in base_url
            or "100.103" in base_url
        ):
            return "local"
        if provider == "google" or "generativelanguage" in base_url:
            return "google"
        if provider == "openrouter" or "openrouter.ai" in base_url:
            return "openrouter"
        return provider

    def _update_stats(self, **kwargs):
        """Thread-safe update of last_run_stats."""
        with self._stats_lock:
            for key, value in kwargs.items():
                if key in self.last_run_stats:
                    if isinstance(self.last_run_stats[key], int):
                        self.last_run_stats[key] += value
                    else:
                        self.last_run_stats[key] = value

    def _effective_confidence_threshold(self, threshold: float) -> float:
        """Lower threshold for Gemini, OpenAI and Local LLMs to account for conservative scoring."""
        provider = self._get_provider()

        if provider in ("google", "local", "openai"):
            res = min(threshold, 0.25)
            logger.info(
                f"DIAGNOSTIC: Applying CONSERVATIVE threshold for {provider}: {threshold} -> {res}"
            )
            return res
        return threshold

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        """
        Normalize confidence to [0, 1].
        Accepts values like 0.78, "0.78", 78, "78%", "78.0%".
        """
        if value is None:
            return 0.5
        if isinstance(value, str):
            text = value.strip().replace("%", "")
            if not text:
                return 0.5
            try:
                value = float(text)
            except ValueError:
                return 0.5
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return 0.5
        if conf > 1.0 and conf <= 100.0:
            conf = conf / 100.0
        if conf < 0.0:
            return 0.0
        if conf > 1.0:
            return 1.0
        return conf

    def analyze_collection_relationships(
        self,
        articles: list[PubTatorArticle],
        nodes_map: dict[str, dict[str, PubTatorNode]],
        max_workers: int = 5,
    ) -> list[SemanticEdge]:
        """
        Analyze a collection of articles in parallel.

        Args:
            articles: List of PubTatorArticle objects
            nodes_map: Dictionary mapping PMID to its nodes (entity_id -> PubTatorNode)
            max_workers: Number of concurrent threads

        Returns:
            Combined list of SemanticEdge objects from all articles
        """
        import concurrent.futures

        all_edges = []
        total = len(articles)
        completed = 0
        succeeded = 0
        failed = 0

        provider = self._get_provider()
        model_name = str(getattr(self.llm_client, "model", "unknown")).lower()

        self.last_article_errors = {}
        # Reset but preserve provider/model info
        with self._stats_lock:
            self.last_run_stats.update(
                {
                    "total_articles": total,
                    "processed_articles": 0,
                    "succeeded_articles": 0,
                    "failed_articles": 0,
                    "api_errors": 0,
                    "parse_failures": 0,
                    "relaxed_recoveries": 0,
                    "compact_retries": 0,
                    "coverage_passes": 0,
                    "coverage_expansions": 0,
                    "dropped_by_threshold": 0,
                    "dropped_invalid_nodes": 0,
                    "provider": provider,
                    "model": model_name,
                }
            )

        # Helper for progress tracking thread safety
        def update_progress(current, count, msg, error=None):
            if self.progress_callback:
                self.progress_callback(current, count, msg, error)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create a future for each article
            future_to_article = {
                executor.submit(
                    self.analyze_article_relationships,
                    article,
                    nodes_map.get(article.pmid, {}),
                    i + 1,
                ): article
                for i, article in enumerate(articles)
            }

            for future in concurrent.futures.as_completed(future_to_article):
                article = future_to_article[future]
                completed += 1
                try:
                    edges = future.result()
                    all_edges.extend(edges)
                    error_msg = self.last_article_errors.get(article.pmid)
                    if error_msg:
                        failed += 1
                        update_progress(completed, total, f"Failed PMID {article.pmid}", error_msg)
                    else:
                        succeeded += 1
                        update_progress(
                            completed,
                            total,
                            f"Completed PMID {article.pmid} ({len(edges)} semantic edges)",
                            None,
                        )
                except Exception as e:
                    failed += 1
                    logger.error(f"Unexpected executor error for {article.pmid}: {e}")
                    update_progress(completed, total, f"Failed PMID {article.pmid}", str(e))

        # Final stats sync
        self._update_stats(
            processed_articles=completed, succeeded_articles=succeeded, failed_articles=failed
        )

        return all_edges

    def analyze_article_relationships(
        self, article: PubTatorArticle, nodes: dict[str, PubTatorNode], article_num: int = 0
    ) -> list[SemanticEdge]:
        """
        Analyze abstract to identify semantic relationships between entities.

        Args:
            article: PubTator article with abstract text
            nodes: Dictionary of nodes (entity_id -> PubTatorNode)
            article_num: Current article number for progress tracking

        Returns:
            List of SemanticEdge objects representing identified relationships
        """
        # Check cache first
        if article.pmid in self.cache:
            logger.debug(f"Using cached semantic edges for PMID {article.pmid}")
            return self.cache[article.pmid]

        # Build entity list for the prompt
        entity_list = self._build_entity_list(nodes)

        if len(entity_list) < 2:
            # Need at least 2 entities to form a relationship
            return []

        if not article.abstract:
            logger.warning(f"No abstract available for PMID {article.pmid}")
            self.last_article_errors.pop(article.pmid, None)
            return []

        provider = self._get_provider()

        # Call LLM with progress update
        try:
            # Select prompt and format based on provider
            if provider == "local":
                # Optimized balanced prompt for local models
                prompt = self._build_local_prompt(article.title, article.abstract, entity_list)
            elif provider == "google":
                # For Gemini, go straight to High-Coverage prompt to avoid 2nd pass latency
                prompt = self._build_coverage_prompt(article.title, article.abstract, entity_list)
            else:
                prompt = self._build_llm_prompt(article.title, article.abstract, entity_list)

            # First pass: Use selected prompt
            # Use a large max_tokens by default for all providers to prevent truncation
            call_kwargs = {"max_tokens": 3000}

            # Enable JSON mode for all providers that support it (including OpenRouter)
            if provider in ("google", "openai", "openrouter"):
                call_kwargs["response_format"] = {"type": "json_object"}

            response = self._call_llm(prompt, **call_kwargs)
            relationships = self._parse_llm_response(response, article.pmid)

            initial_recall = len(relationships)
            entity_count = len(entity_list)

            # Threshold for triggering a recovery pass:
            # - More aggressive threshold to ensure high recall, especially for complex abstracts
            RECOVERY_THRESHOLD = max(2, entity_count // 3)

            # --- Provider-specific recovery and enhancement ---

            # 1. Global Recovery Strategy (only when first pass is meaningfully below threshold)
            if initial_recall < RECOVERY_THRESHOLD and entity_count >= 2:
                # Decide if we need a second pass or just a compact retry
                if initial_recall == 0:
                    self._update_stats(compact_retries=1)
                    coverage_prompt = self._build_compact_retry_prompt(
                        article.title, article.abstract, entity_list
                    )
                    pass_name = "compact-retry"
                else:
                    self._update_stats(coverage_passes=1)
                    coverage_prompt = self._build_coverage_prompt(
                        article.title, article.abstract, entity_list
                    )
                    pass_name = "coverage-pass"

                # Global recovery pass
                coverage_response = self._call_llm(coverage_prompt, max_tokens=2000)
                coverage_rels = self._parse_llm_response(coverage_response, article.pmid)

                # Merge results using robust sorted-pair deduplication
                existing_pairs = set()
                for r in relationships:
                    e1, e2 = sorted([str(r.get("entity1_id", "")), str(r.get("entity2_id", ""))])
                    existing_pairs.add((e1, e2, str(r.get("relation_type"))))

                expanded_count = 0
                for r in coverage_rels:
                    e1, e2 = sorted([str(r.get("entity1_id", "")), str(r.get("entity2_id", ""))])
                    pair = (e1, e2, str(r.get("relation_type")))
                    if pair not in existing_pairs:
                        relationships.append(r)
                        existing_pairs.add(pair)
                        expanded_count += 1

                if expanded_count > 0:
                    self._update_stats(coverage_expansions=1)
                    logger.info(
                        f"PMID {article.pmid}: Adaptive {pass_name} expanded {initial_recall} -> {len(relationships)} relationships (+{expanded_count})"
                    )

            # 3. Final safety check: only retry for local LLM if still empty
            # (OpenAI/Gemini trust: empty = nothing found, no retry to preserve speed)
            if not relationships and len(entity_list) >= 2 and provider == "local":
                self._update_stats(compact_retries=1)
                retry_prompt = self._build_compact_retry_prompt(
                    article.title, article.abstract, entity_list
                )
                response = self._call_llm(retry_prompt, max_tokens=1000)
                relationships = self._parse_llm_response(response, article.pmid)

        except Exception as e:
            err_str = str(e)
            logger.error(f"Error during semantic analysis for PMID {article.pmid}: {e}")
            self.last_article_errors[article.pmid] = err_str
            # Count API/call failures separately from parse failures
            self._update_stats(api_errors=1)
            return []

        # Filter by confidence and convert to SemanticEdge
        semantic_edges = []
        dropped_by_threshold = 0
        dropped_by_invalid_nodes = 0
        effective_threshold = self._effective_confidence_threshold(self.confidence_threshold)
        for rel in relationships:
            node1 = rel["entity1_id"]
            node2 = rel["entity2_id"]

            # More robust ID cleaning - handle "ID: Name" or "ID (Name)" patterns
            def extract_base_id(raw_id: str) -> str:
                # 1. Handle "MESH:D000001_Disease: Name"
                if ": " in raw_id:
                    raw_id = raw_id.split(": ")[0]
                # 2. Handle "MESH:D000001_Disease (Name)"
                if " (" in raw_id:
                    raw_id = raw_id.split(" (")[0]
                # 3. Handle "[MESH:D000001_Disease]" (common in some model outputs)
                return raw_id.strip().strip("[]").strip()

            node1 = extract_base_id(node1)
            node2 = extract_base_id(node2)

            # Repair IDs: strict prefix-based repair only (no name-based fallback).
            if node1 not in nodes:
                # Try prefix match
                matches = [
                    n_id
                    for n_id in nodes
                    if n_id.startswith(node1)
                    and (len(n_id) == len(node1) or n_id[len(node1)] in ("_", ";"))
                ]
                if len(matches) >= 1:
                    node1 = matches[0]
                    rel["entity1_id"] = node1

            if node2 not in nodes:
                matches = [
                    n_id
                    for n_id in nodes
                    if n_id.startswith(node2)
                    and (len(n_id) == len(node2) or n_id[len(node2)] in ("_", ";"))
                ]
                if len(matches) >= 1:
                    node2 = matches[0]
                    rel["entity2_id"] = node2

            # Only add if both nodes are valid
            if node1 in nodes and node2 in nodes:
                confidence = self._normalize_confidence(rel.get("confidence"))
                if confidence >= effective_threshold:
                    # Ensure alphabetical ordering for consistency
                    # (Though GraphEdge handles direction, having consistent storage is nice)
                    # But wait, SemanticEdge stores node1/node2 as is, relation has direction.
                    # We should keep order matched to relation.

                    edge = SemanticEdge(
                        node1_id=node1,
                        node2_id=node2,
                        pmid=article.pmid,
                        relation_type=rel.get("relation_type", "related_to"),
                        confidence=confidence,
                        evidence=rel.get("evidence", ""),
                    )
                    semantic_edges.append(edge)
                else:
                    dropped_by_threshold += 1
            else:
                dropped_by_invalid_nodes += 1
                logger.warning(
                    f"PMID {article.pmid}: Skipping edge with invalid nodes: {node1}, {node2}"
                )

        # Cache results
        self.cache[article.pmid] = semantic_edges
        self.last_article_errors.pop(article.pmid, None)
        self._update_stats(
            dropped_by_threshold=dropped_by_threshold,
            dropped_invalid_nodes=dropped_by_invalid_nodes,
        )

        logger.info(
            f"PMID {article.pmid}: Found {len(semantic_edges)} semantic relationships "
            f"from {len(entity_list)} entities "
            f"(threshold={effective_threshold:.2f}, dropped_threshold={dropped_by_threshold}, "
            f"dropped_invalid_nodes={dropped_by_invalid_nodes})"
        )

        return semantic_edges

    def _build_entity_list(self, nodes: dict[str, PubTatorNode]) -> list[dict[str, str]]:
        """Build a structured entity list for the LLM prompt"""
        entity_list = []
        for node_id, node in nodes.items():
            entity_list.append(
                {"id": node_id, "name": node.name, "type": node.type, "mesh": node.mesh}
            )
        return entity_list

    @staticmethod
    def _allowed_relation_types() -> list[str]:
        # Canonical set aligned with project relation taxonomy used by ChatGPT prompts.
        allowed = sorted((DIRECTIONAL_RELATIONS | SYMMETRIC_RELATIONS) - {"co-mention"})
        return allowed

    def _build_llm_prompt(
        self, title: str, abstract: str, entity_list: list[dict[str, str]]
    ) -> str:
        """
        Construct a detailed prompt for LLM relationship extraction.

        The prompt instructs the LLM to:
        1. Analyze the abstract for entity relationships
        2. Return structured JSON with relationships
        3. Include confidence scores and supporting evidence
        """
        entity_descriptions = "\n".join(
            [f"- {ent['id']}: {ent['name']} (Type: {ent['type']})" for ent in entity_list]
        )
        allowed_relations = ", ".join(self._allowed_relation_types())
        pair_count = len(entity_list) * (len(entity_list) - 1) // 2

        prompt = f"""You are a biomedical research assistant analyzing scientific abstracts to identify relationships between entities.

**Task**: Analyze the following abstract and identify EXPLICIT relationships between the provided entities. Only include relationships that are clearly stated or strongly implied in the text.

**Title**: {title}

**Abstract**: {abstract}

**Entities**:
{entity_descriptions}

**Instructions**:
1. Treat all entity pairs co-mentioned in this article as candidate pairs ({pair_count} unordered pairs).
2. For each candidate pair, decide whether a biomedical relation is supported by abstract evidence.
3. Output only supported pairs as relations.
4. For each relationship, determine:
-   - The two entities involved (use their IDs)
-   - The relationship type (must be one of: {allowed_relations})
-   - Confidence score (0-1): How confident are you this relationship is explicitly stated? **Do not reuse the sample value; personalize it for each edge.**
-   - Supporting evidence: The specific sentence or phrase supporting this relationship

4. Return ONLY a JSON array with this exact structure:
[
  {{
    "entity1_id": "...",
    "entity2_id": "...",
    "relation_type": "...",
    "confidence": 0.41,
    "evidence": "exact quote from abstract"
  }}
]

**Important**:
- Do NOT perform NER. PubTator3 already provided entities; only classify relations between those IDs.
- Use only the canonical relation_type values listed above.
- Only include relationships explicitly mentioned in the abstract
- Do not infer relationships from general knowledge
- If no clear relationships exist, return an empty array: []
- Ensure evidence text does not contain double-quote characters
- Return ONLY valid JSON, no additional text or markdown
"""

        return prompt

    def _build_compact_retry_prompt(
        self, title: str, abstract: str, entity_list: list[dict[str, str]]
    ) -> str:
        """
        Compact retry prompt for Gemini/OpenAI when the first pass yields no parsable relations.
        Keeps output schema minimal for higher JSON stability and recall.
        """
        entity_descriptions = "\n".join(
            [f"- {ent['id']}: {ent['name']} (Type: {ent['type']})" for ent in entity_list]
        )
        allowed_relations = ", ".join(self._allowed_relation_types())
        pair_count = len(entity_list) * (len(entity_list) - 1) // 2
        return f"""You are a biomedical relationship extractor.

Return ONLY a valid JSON array. No markdown, no commentary.

Title: {title}
Abstract: {abstract}
Entities:
{entity_descriptions}

Rules:
1. Treat all entity pairs co-mentioned in this article as candidate pairs ({pair_count} unordered pairs).
2. Use only IDs listed in Entities.
3. Do NOT perform NER. Do not introduce new entities.
4. Output each relation as:
   {{
     "entity1_id": "...",
     "entity2_id": "...",
     "relation_type": "...",
     "confidence": 0.0 to 1.0
   }}
5. relation_type must be one of: {allowed_relations}
6. Keep only explicit or strongly implied relations from the abstract.
7. If none, return [].
"""

    def _build_coverage_prompt(
        self, title: str, abstract: str, entity_list: list[dict[str, str]]
    ) -> str:
        """
        Coverage-oriented prompt used as second pass for Gemini when recall is low.
        """
        entity_descriptions = "\n".join(
            [f"- {ent['id']}: {ent['name']} (Type: {ent['type']})" for ent in entity_list]
        )
        allowed_relations = ", ".join(self._allowed_relation_types())
        pair_count = len(entity_list) * (len(entity_list) - 1) // 2

        return f"""You are a biomedical relation classifier.

Return ONLY a valid JSON array. No markdown, no commentary.

Title: {title}
Abstract: {abstract}
Entities:
{entity_descriptions}

Task:
- Do NOT perform NER. Use only listed entity IDs.
- Treat all co-mentioned entity pairs as candidates ({pair_count} unordered pairs).
- Extract as many explicit or strongly implied relations as supported by the abstract.
- **CRITICAL**: Prioritize recall. Do not overlook subtle but explicit connections.

Output format:
[
  {{
    "entity1_id": "ID from Entities",
    "entity2_id": "ID from Entities",
    "relation_type": "one of: {allowed_relations}",
    "confidence": 0.0 to 1.0,
    "evidence": "sentence from abstract"
  }}
]

If no relations are found, return [].
"""

    def _build_local_prompt(
        self, title: str, abstract: str, entity_list: list[dict[str, str]]
    ) -> str:
        """Concise and structured prompt optimized for local models (e.g., Llama 3, Mistral)."""
        entity_block = "\n".join([f"- {e['id']}: {e['name']}" for e in entity_list])
        allowed = ", ".join(self._allowed_relation_types())

        return f"""### Task: Extract Biomedical Relationships
Analyze the abstract below and list all specific relationships between the given entities.

### Entities:
{entity_block}

### Abstract:
Title: {title}
{abstract}

### Instructions:
1. Identify relationships only from the list: {allowed}.
2. For each relationship, provide: entity1_id, entity2_id, relation_type, confidence (0-1), and evidence.
3. Be EXTREMELY thorough. Extract every mentioned interaction.
4. Output ONLY a JSON array of objects. No preamble.

### JSON Output:
"""

    def _call_llm(
        self, prompt: str, max_tokens: int = 1500, response_format: dict | None = None
    ) -> str:
        """Call the LLM API with the constructed prompt"""
        provider = self._get_provider()
        if not self.llm_client or not self.llm_client.client:
            # Google provider may use direct HTTP helper without SDK client state.
            if provider != "google":
                raise ValueError("LLM client not initialized")

        system_instruction = (
            "You are an expert in biomedical relationship extraction. "
            "You analyze scientific abstracts and identify relationships between entities. "
            "Always respond with valid JSON."
        )
        max_retries = 5
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"DIAGNOSTIC: Initiating LLM call (provider={provider}, max_tokens={max_tokens})"
                )
                response_text = self.llm_client.chat_completion_text(
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=max_tokens,
                    timeout=180.0,
                    response_format=response_format,
                )
                preview = (response_text[:400] + "...") if len(response_text) > 400 else response_text
                logger.info(f"DIAGNOSTIC: LLM Response preview: {preview}")
                return response_text
            except Exception as e:
                err = str(e).lower()
                is_rate_limit = any(t in err for t in ("429", "rate limit", "quota", "resource exhausted", "too many requests"))
                if is_rate_limit and attempt < max_retries - 1:
                    wait = 15 * (2 ** attempt)  # 15s, 30s, 60s, 120s
                    logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries}), waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    logger.error(f"LLM call failed: {e}")
                    raise

    def _parse_llm_response(self, response: str, pmid: str) -> list[dict[str, Any]]:
        """
        Parse LLM response into structured relationship data.

        Handles various response formats and performs validation.
        """
        # If the response is empty or whitespace, return immediately
        # This is NOT a parse failure - the model may simply have nothing to report
        if not response or not response.strip():
            logger.debug(f"PMID {pmid}: Empty LLM response (no relationships found)")
            return []

        # Clean up markdown code blocks if present
        text = response.strip()
        if "```" in text:
            # Try to extract content between code fences
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if json_match:
                text = json_match.group(1).strip()

        # If no code fences, or regex failed, try to find the first significant JSON structure
        # We look for the most encompassing [] or {} block

        # Priority 1: Find the first '[' and last ']'
        array_match = re.search(r"\[[\s\S]*\]", text)
        # Priority 2: Find the first '{' and last '}'
        object_match = re.search(r"\{[\s\S]*\}", text)

        if array_match and object_match:
            # Use whichever comes first and ends last (most encompassing)
            if array_match.start() < object_match.start():
                text = array_match.group(0)
            else:
                text = object_match.group(0)
        elif array_match:
            text = array_match.group(0)
        elif object_match:
            text = object_match.group(0)

        try:
            data = json.loads(text)

            # Handle potential object wrapping (e.g., {"relationships": [...]})
            if isinstance(data, dict):
                # Search for any list value within the object
                for val in data.values():
                    if isinstance(val, list):
                        relationships = val
                        break
                else:
                    # If it's a single relation object, wrap it
                    if all(k in data for k in ["entity1_id", "entity2_id"]):
                        relationships = [data]
                    else:
                        relationships = []
            else:
                relationships = data

            if not isinstance(relationships, list):
                logger.warning(f"PMID {pmid}: LLM returned non-list response")
                return []

            # Validate each relationship
            validated = []
            for rel in relationships:
                if not isinstance(rel, dict):
                    continue

                required_fields = ["entity1_id", "entity2_id", "relation_type"]
                if all(field in rel for field in required_fields):
                    rel["relation_type"] = normalize_relation_type(
                        str(rel.get("relation_type", ""))
                    )
                    # Ensure confidence is a float
                    rel["confidence"] = self._normalize_confidence(rel.get("confidence"))

                    # Ensure evidence is a string
                    if "evidence" not in rel:
                        rel["evidence"] = ""

                    validated.append(rel)
                else:
                    logger.warning(f"PMID {pmid}: Skipping malformed relationship: {rel}")

            return validated

        except json.JSONDecodeError as e:
            self._update_stats(parse_failures=1)
            logger.error(f"PMID {pmid}: Failed to parse LLM response as JSON: {e}")
            relaxed = self._parse_llm_response_relaxed(text, pmid)
            if relaxed:
                self._update_stats(relaxed_recoveries=1)
                logger.info(
                    f"PMID {pmid}: Recovered {len(relaxed)} relationships via relaxed parser"
                )
                return relaxed
            logger.debug(f"Raw response: {response}")
            return []

    def _parse_llm_response_relaxed(self, text: str, pmid: str) -> list[dict[str, Any]]:
        """
        Best-effort parser for malformed JSON-like outputs.
        Extracts repeated relationship fields even if the JSON structure is invalid.
        """

        # Helper to extract values even if keys are unquoted or quotes are mismatching
        def _extract(field_name: str, chunk: str, default: str = "") -> str:
            # Regex designed to handle:
            # 1. key: "value"
            # 2. "key": "value"
            # 3. key: 'value' (single quotes)
            # 4. key: value (unquoted if no space)
            # 5. Handle escaped quotes within value

            # Pattern for: key_name (optional quotes) : (optional quotes) value (optional quotes)
            pattern = rf'[\'"]?{field_name}[\'"]?\s*:\s*([\'"])(.*?)\1'
            match = re.search(pattern, chunk, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(2).strip()

            # Fallback for unquoted numerical or single-word values (like confidence)
            pattern_noquote = rf'[\'"]?{field_name}[\'"]?\s*:\s*([^,\s\}}\]]+)'
            match = re.search(pattern_noquote, chunk, flags=re.IGNORECASE)
            if match:
                res = match.group(1).strip().strip("\",'")
                return res

            return default

        # Find potential object blocks
        chunks = re.findall(r"\{[\s\S]*?\}", text)
        if not chunks:
            # If no {}, look for common bulleted list patterns or line-based pairs
            # This handles cases where models omit braces but keep property-like lines
            # Example: "entity1_id: ID1, entity2_id: ID2, relation_type: Inhibits..."
            lines = text.split("\n")
            current_chunk = []
            for line in lines:
                if any(k in line for k in ["entity1_id", "entity2_id", "relation_type"]):
                    current_chunk.append(line)
                elif current_chunk:
                    # End of a potential logical block
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
            if current_chunk:
                chunks.append("\n".join(current_chunk))

        if not chunks:
            chunks = [text]

        recovered: list[dict[str, Any]] = []
        for chunk in chunks:
            entity1 = _extract("entity1_id", chunk)
            entity2 = _extract("entity2_id", chunk)
            relation = _extract("relation_type", chunk)
            conf_str = _extract("confidence", chunk, "0.5")
            evidence = _extract("evidence", chunk, "")

            if not (entity1 and entity2 and relation):
                continue
            confidence = self._normalize_confidence(conf_str)

            recovered.append(
                {
                    "entity1_id": entity1,
                    "entity2_id": entity2,
                    "relation_type": relation,
                    "confidence": confidence,
                    "evidence": evidence,
                }
            )

        return recovered

    def convert_to_pubtator_edges(self, semantic_edges: list[SemanticEdge]) -> list[PubTatorEdge]:
        """
        Convert SemanticEdge objects to PubTatorEdge format.

        Now preserves confidence and evidence metadata.

        Args:
            semantic_edges: List of SemanticEdge objects

        Returns:
            List of PubTatorEdge objects with semantic metadata
        """
        pubtator_edges = []
        for se in semantic_edges:
            edge = PubTatorEdge(
                node1_id=se.node1_id,
                node2_id=se.node2_id,
                pmid=se.pmid,
                relation=se.relation_type,
                confidence=se.confidence,  # Preserve confidence score
                evidence=se.evidence,  # Preserve supporting evidence
                source_id=se.node1_id,  # Explicitly mark node1 as source
            )
            pubtator_edges.append(edge)

        return pubtator_edges

    def clear_cache(self):
        """Clear the cached results"""
        self.cache.clear()
        logger.info("Semantic analysis cache cleared")

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about the cache"""
        return {
            "cached_articles": len(self.cache),
            "total_edges": sum(len(edges) for edges in self.cache.values()),
        }
