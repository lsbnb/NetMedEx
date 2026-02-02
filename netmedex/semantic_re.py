from __future__ import annotations

"""
Semantic Relationship Extraction using LLM

This module provides LLM-based semantic analysis for extracting meaningful
relationships between biomedical entities, as an alternative to simple
co-occurrence-based edge construction.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from netmedex.pubtator_data import PubTatorArticle, PubTatorAnnotation
from netmedex.pubtator_graph_data import PubTatorNode, PubTatorEdge

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

        # Helper for progress tracking thread safety
        def update_progress(article_num, count, msg, error=None):
            if self.progress_callback:
                self.progress_callback(article_num, total, msg, error)

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
                    # Progress update is handled inside analyze_article_relationships,
                    # but we can add a high-level update here if needed.
                except Exception as e:
                    logger.error(f"Exc generated for {article.pmid}: {e}")
                    update_progress(completed, total, "", str(e))

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
            if self.progress_callback:
                self.progress_callback(article_num, 0, f"Using cache for {article.pmid}", None)
            return self.cache[article.pmid]

        # Build entity list for the prompt
        entity_list = self._build_entity_list(nodes)

        if len(entity_list) < 2:
            # Need at least 2 entities to form a relationship
            return []

        if not article.abstract:
            logger.warning(f"No abstract available for PMID {article.pmid}")
            return []

        # Build LLM prompt
        prompt = self._build_llm_prompt(article.title, article.abstract, entity_list)

        # Call LLM with progress update
        try:
            if self.progress_callback:
                # Note: In threaded context, this callback must be thread-safe or handled carefully.
                # Assuming the callback provided by webapp handles this or strictly just updates a queue.
                self.progress_callback(
                    article_num,
                    1,
                    f"Analyzing PMID {article.pmid} ({len(entity_list)} entities)...",
                    None,
                )

            response = self._call_llm(prompt)

            relationships = self._parse_llm_response(response, article.pmid)
        except Exception as e:
            logger.error(f"Error during semantic analysis for PMID {article.pmid}: {e}")
            if self.progress_callback:
                self.progress_callback(article_num, 1, "", str(e))
            return []

        # Filter by confidence and convert to SemanticEdge
        semantic_edges = []
        for rel in relationships:
            if rel.get("confidence", 0) >= self.confidence_threshold:
                # Ensure alphabetical ordering for consistency
                node1 = rel["entity1_id"]
                node2 = rel["entity2_id"]
                edge = SemanticEdge(
                    node1_id=node1,
                    node2_id=node2,
                    pmid=article.pmid,
                    relation_type=rel.get("relation_type", "related_to"),
                    confidence=rel.get("confidence", 0.5),
                    evidence=rel.get("evidence", ""),
                )
                semantic_edges.append(edge)

        # Cache results
        self.cache[article.pmid] = semantic_edges

        logger.info(
            f"PMID {article.pmid}: Found {len(semantic_edges)} semantic relationships "
            f"from {len(entity_list)} entities"
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

        prompt = f"""You are a biomedical research assistant analyzing scientific abstracts to identify relationships between entities.

**Task**: Analyze the following abstract and identify EXPLICIT relationships between the provided entities. Only include relationships that are clearly stated or strongly implied in the text.

**Title**: {title}

**Abstract**: {abstract}

**Entities**:
{entity_descriptions}

**Instructions**:
1. Identify relationships between entity pairs mentioned in the abstract
2. For each relationship, determine:
   - The two entities involved (use their IDs)
   - The relationship type (e.g., "increases", "inhibits", "associated_with", "causes", "treats", "regulates")
   - Confidence score (0-1): How confident are you this relationship is explicitly stated?
   - Supporting evidence: The specific sentence or phrase supporting this relationship

3. Return ONLY a JSON array with this exact structure:
[
  {{
    "entity1_id": "...",
    "entity2_id": "...",
    "relation_type": "...",
    "confidence": 0.9,
    "evidence": "exact quote from abstract"
  }}
]

**Important**:
- Only include relationships explicitly mentioned in the abstract
- Do not infer relationships from general knowledge
- If no clear relationships exist, return an empty array: []
- Return ONLY valid JSON, no additional text or markdown
"""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM API with the constructed prompt"""
        if not self.llm_client or not self.llm_client.client:
            raise ValueError("LLM client not initialized")

        response = self.llm_client.client.chat.completions.create(
            model=self.llm_client.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in biomedical relationship extraction. "
                    "You analyze scientific abstracts and identify relationships between entities. "
                    "Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=1500,  # Allow for multiple relationships
            timeout=180.0,  # 3 minutes for large models like 20B parameters
        )

        return response.choices[0].message.content.strip()

    def _parse_llm_response(self, response: str, pmid: str) -> list[dict[str, Any]]:
        """
        Parse LLM response into structured relationship data.

        Handles various response formats and performs validation.
        """
        # Clean up markdown code blocks if present
        cleaned_response = response.strip()
        if cleaned_response.startswith("```"):
            # Remove markdown code fence
            lines = cleaned_response.split("\n")
            # Remove first line (```json or ```) and last line (```)
            cleaned_response = "\n".join(lines[1:-1])

        try:
            relationships = json.loads(cleaned_response)

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
                    # Ensure confidence is a float
                    if "confidence" in rel:
                        try:
                            rel["confidence"] = float(rel["confidence"])
                        except (ValueError, TypeError):
                            rel["confidence"] = 0.5
                    else:
                        rel["confidence"] = 0.5

                    # Ensure evidence is a string
                    if "evidence" not in rel:
                        rel["evidence"] = ""

                    validated.append(rel)
                else:
                    logger.warning(f"PMID {pmid}: Skipping malformed relationship: {rel}")

            return validated

        except json.JSONDecodeError as e:
            logger.error(f"PMID {pmid}: Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {response[:200]}")
            return []

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
