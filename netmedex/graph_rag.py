from __future__ import annotations

import logging
import re
from collections import Counter
from itertools import islice

import networkx as nx

from netmedex.claim_verifier import relation_supported_by_text
from netmedex.community import CommunityDetector, GraphCommunity
from netmedex.graph_schema import graph_schema_status
from netmedex.relation_types import is_directional_relation, relation_polarity
from netmedex.utils import generate_stable_id

logger = logging.getLogger(__name__)


class GraphRetriever:
    """
    Retrieves structured context from the knowledge graph for Hybrid RAG.
    """

    # Ontology Preference: Prioritize Genes and Diseases while ignoring non-biomedical noise.
    # "pathway" was previously listed here but nothing ever produces a node of that type -- removed.
    VALID_NODE_TYPES = {
        "gene", "disease", "chemical", "variant", "cellline",
        "biologicalprocess", "phenotype", "pathway",
    }
    IGNORED_NODE_TYPES = {"species", "entity", "geographic area", "organism"}

    TYPE_WEIGHTS = {"gene": 1.2, "disease": 1.2, "chemical": 1.1, "variant": 1.1}
    NEGATIVE_RELATIONS = {
        "inhibits",
        "suppresses",
        "downregulates",
        "decreases",
        "prevents",
        "blocks",
        "ameliorates",
        "treats",
    }
    # ``treats`` describes an intervention/outcome relation, not a signed
    # biological influence that can safely be composed through another edge.
    # It remains valid as a direct one-hop retrieval fact, but a path such as
    # ``dysbiosis --decreases--> serotonin --treats--> bone disease`` must not
    # be promoted into a causal claim about dysbiosis and bone disease.
    NON_COMPOSABLE_MULTI_HOP_RELATIONS = {"treats"}
    MULTILINGUAL_QUERY_ALIASES = (
        ("腎臟保護", " kidney protection "),
        ("肾脏保护", " kidney protection "),
        ("腎保護", " kidney protection "),
        ("肾保护", " kidney protection "),
        ("抑制劑", " inhibitor "),
        ("抑制剂", " inhibitor "),
        ("腎臟", " kidney "),
        ("肾脏", " kidney "),
    )

    DEFAULT_CLAIM_CONFIDENCE_THRESHOLD = 0.8

    def __init__(
        self,
        graph: nx.Graph,
        node_rag=None,
        claim_confidence_threshold: float = DEFAULT_CLAIM_CONFIDENCE_THRESHOLD,
    ):
        """
        Initialize the Graph Retriever.

        Args:
            graph: The NetworkX graph containing the knowledge network.
            node_rag: Optional NodeRAG instance for semantic search.
        """
        self.graph = graph
        if not 0.0 <= float(claim_confidence_threshold) <= 1.0:
            raise ValueError("claim_confidence_threshold must be between 0 and 1")
        self.claim_confidence_threshold = float(claim_confidence_threshold)
        self.schema_status = graph_schema_status(graph)
        if self.schema_status["rebuild_required"]:
            logger.warning(
                "GraphRetriever received a stale frozen graph; Pathway/Process/Phenotype "
                "coverage is incomplete until rebuild: %s",
                ", ".join(self.schema_status["reasons"]),
            )
        self.node_rag = node_rag
        self.last_candidate_audit: list[dict] = []
        self._build_node_index()
        self.community_detector: CommunityDetector = CommunityDetector(self.graph)

    def _build_node_index(self):
        """Build a case-insensitive index of node names to IDs."""
        self.name_to_id = {}
        for node_id, data in self.graph.nodes(data=True):
            # Index the primary ID
            self.name_to_id[str(node_id).lower()] = node_id

            # Index the 'name' attribute if it exists
            if "name" in data and data["name"]:
                self.name_to_id[str(data["name"]).lower()] = node_id

    def find_relevant_nodes(self, query: str) -> list[str]:
        """
        Identify nodes in the graph that are relevant to the user query.

        Strategy: Hybrid Search
        1. Exact/Substring matching (High precision)
        2. Vector Semantic matching (High recall) - via NodeRAG

        Args:
            query: User's natural language query.

        Returns:
            List of unique node IDs found in the query.
        """
        query_lower = query.lower()
        normalized_query = self._normalize_anchor_text(query)
        matched_nodes = set()

        # 1. Exact/Substring Matching
        sorted_names: list[str] = sorted(self.name_to_id.keys(), key=len, reverse=True)
        for name in sorted_names:
            if name in query_lower or self._normalize_anchor_text(name) in normalized_query:
                matched_nodes.add(self.name_to_id[name])

        # 2. Semantic Vector Matching (if available)
        if self.node_rag:
            logger.info("Performing semantic node search...")
            # Use a threshold to avoid irrelevant matches
            semantic_hits = self.node_rag.search_nodes(query, top_k=5)
            for node_id, score, meta in semantic_hits:
                # Acceptance threshold (0.6 is a reasonable starting point for inverted L2)
                if score > 0.6:
                    matched_nodes.add(node_id)
                    logger.info(f"  + Semantic match: {meta.get('name')} (Score: {score:.2f})")

        return list(matched_nodes)

    def find_relevant_communities(
        self,
        query: str,
        matched_node_ids: list[str] | None = None,
        top_k: int = 2,
    ) -> list[tuple[GraphCommunity, float]]:
        """
        Identify top macro-level topological communities relevant to the user query.
        """
        return self.community_detector.match_communities(
            query=query, matched_node_ids=matched_node_ids, top_k=top_k
        )

    def get_macro_community_context(
        self,
        query: str | None = None,
        relevant_nodes: list[str] | None = None,
        top_k: int = 2,
    ) -> str:
        """
        Extract textual overview for top-ranked macro-level functional communities.
        """
        q = query or ""
        matched = self.find_relevant_communities(
            query=q, matched_node_ids=relevant_nodes, top_k=top_k
        )
        if not matched:
            return ""

        lines = ["### Macro-Level Functional Communities:"]
        for comm, score in matched:
            lines.append(
                f"- **[{comm.title}]** (Relevance: {score:.2f}, Nodes: {comm.node_count}, Edges: {comm.edge_count})"
            )
            hub_parts = []
            if comm.gene_hubs:
                hub_parts.append(f"Genes: {', '.join(comm.gene_hubs)}")
            if comm.disease_hubs:
                hub_parts.append(f"Diseases: {', '.join(comm.disease_hubs)}")
            if comm.drug_hubs:
                hub_parts.append(f"Chemicals/Drugs: {', '.join(comm.drug_hubs)}")
            if comm.phenotype_hubs:
                hub_parts.append(f"Phenotypes/Pathways: {', '.join(comm.phenotype_hubs)}")
            elif comm.top_hubs and not hub_parts:
                hub_parts.append(f"Top Hubs: {', '.join(comm.top_hubs)}")

            if hub_parts:
                lines.append(f"  - **Hub Entities**: {'; '.join(hub_parts)}")
            lines.append(f"  - **Functional Summary**: {comm.summary}")
            if comm.top_pmids:
                pmid_str = ", ".join(f"[PMID:{p}]" for p in comm.top_pmids[:3])
                lines.append(f"  - **Key PMIDs**: {pmid_str}")

        return "\n".join(lines)

    def get_subgraph_context(
        self, relevant_nodes: list[str], query: str | None = None, max_hops: int = 2
    ) -> str:
        """
        Extract textual context describing the subgraph relevant to the nodes.
        Thin wrapper around get_subgraph_context_with_paths() for backward compatibility.
        """
        text, _ = self.get_subgraph_context_with_paths(
            relevant_nodes, query=query, max_hops=max_hops
        )
        return text

    def get_subgraph_context_with_paths(
        self, relevant_nodes: list[str], query: str | None = None, max_hops: int = 2
    ) -> tuple[str, list[dict]]:
        """
        Extract textual context AND structured path data for 2-hop Graph RAG.

        Strategy: Hybrid Scoring 2.0
        Combines Topological NPMI + Semantic Confidence + Query Relevance.

        Args:
            relevant_nodes: List of starting node IDs.
            query: User's original query for semantic relevance scoring.
            max_hops: Maximum number of hops for pathfinding.

        Returns:
            Tuple of (formatted_text, structured_paths) where structured_paths is a list of dicts:
            [{"path": [id1, id2, id3], "names": [name1, name2, name3],
              "score": 0.72, "hop_count": 2}, ...]
        """
        self.last_candidate_audit = []
        if not relevant_nodes:
            return "No specific entities from the graph were found in the query.", []

        # Filter nodes to ensure they exist in the current graph
        valid_nodes = [n for n in relevant_nodes if self.graph.has_node(n)]

        if not valid_nodes:
            return "Identified entities are not present in the current subnetwork.", []

        context_lines = []

        # The traversal already scores the full candidate set before truncation,
        # so retaining 60 records here does not add another semantic-search call.
        candidate_records = self._extract_top_k_paths(
            valid_nodes,
            query=query,
            max_hops=max_hops,
            top_k=60,
            include_anchor_details=True,
        )
        if not candidate_records:
            context_lines.append("[DIRECTIONAL MECHANISTIC EDGES: NO]")
            context_lines.append("[ZERO-TIER-A RESCUE: NOT AVAILABLE]")
            context_lines.append(
                "No significant relational paths could be found for the queried entities."
            )
        else:
            candidate_paths = [
                self._build_structured_path_entry(record, rank)
                for rank, record in enumerate(candidate_records, start=1)
            ]
            self.last_candidate_audit = candidate_paths
            structured_paths, rescue_triggered, rescue_outcome = (
                self._select_gated_candidate_paths(candidate_paths)
            )

            has_directional_edges = any(
                path["claim_safe"] and any(path["edge_is_directional"])
                for path in structured_paths
            )
            dir_flag = "YES" if has_directional_edges else "NO"
            # Root-cause visibility for Layer 3 quality: logs whether this turn even
            # has a directional edge to reason over, so degenerate/Layer-2-like Layer 3
            # output can be attributed to "no directional edges available" (usually an
            # edge_method=co-occurrence graph) vs. other causes (e.g. token truncation).
            logger.info(
                "Layer 3 directional-edge availability: %s (claim-safe paths=%d/%d candidates)",
                dir_flag,
                sum(1 for path in structured_paths if path["claim_safe"]),
                len(structured_paths),
            )
            rescue_flag = "YES" if rescue_triggered else "NO"
            context_lines.append("[DIRECTIONAL MECHANISTIC EDGES: NO]")
            context_lines.append(
                f"[ZERO-TIER-A RESCUE: {rescue_flag}; OUTCOME: {rescue_outcome}]"
            )
            context_lines.append(
                "[CLAIM-SAFE DIVERSITY EXPANSION: "
                f"{sum(bool(path.get('diversity_added')) for path in structured_paths)}]"
            )
            context_lines.append(
                "Latent Network Mechanisms (ranked by Confidence+Topology+Query Anchors):"
            )
            for path in structured_paths:
                if path["retrieval_safe"]:
                    usage = "CLAIM-SAFE" if path["claim_safe"] else "RETRIEVAL-ONLY"
                    rescue_label = " RESCUED" if path["rescue_added"] else ""
                    diversity_label = " DIVERSITY" if path.get("diversity_added") else ""
                    context_lines.append(
                        f"- [GATE TIER {path['gate_tier']}; "
                        f"{usage}{rescue_label}{diversity_label}] "
                        f"{self._format_path(path['node_ids'])} (Score: {path['score']:.2f})"
                    )
            context_lines[0] = f"[DIRECTIONAL MECHANISTIC EDGES: {dir_flag}]"
            if not any(path["retrieval_safe"] for path in structured_paths):
                context_lines.append("No query-aligned graph paths passed the retrieval gate.")

        # Inject Macro-Level Functional Communities
        macro_community_context = self.get_macro_community_context(
            query=query, relevant_nodes=valid_nodes, top_k=2
        )
        if macro_community_context:
            context_lines.append("")
            context_lines.append(macro_community_context)

        return "\n".join(context_lines), (structured_paths if candidate_records else [])

    @staticmethod
    def _select_gated_candidate_paths(
        candidate_paths: list[dict], strict_limit: int = 20, diversity_limit: int = 3
    ) -> tuple[list[dict], bool, str]:
        """Select strict/rescued paths and add bounded, claim-safe bridge diversity."""
        strict_paths = list(candidate_paths[:strict_limit])
        rescue_triggered = not any(path["claim_safe"] for path in strict_paths)
        rescue_outcome = "not_needed"
        if rescue_triggered:
            claim_safe = [path for path in candidate_paths if path["claim_safe"]]
            retrieval_only = [
                path
                for path in candidate_paths
                if path["retrieval_safe"] and not path["claim_safe"]
            ]
            if claim_safe:
                rescue_outcome = "tier_a_recovered"
                selected = (claim_safe[:10] + retrieval_only)[:strict_limit]
            elif retrieval_only:
                rescue_outcome = "tier_b_retrieval_only"
                selected = retrieval_only[:strict_limit]
            else:
                rescue_outcome = "no_usable_path"
                selected = strict_paths
        else:
            selected = strict_paths

        diversity_ids: set[int] = set()
        if not rescue_triggered and diversity_limit > 0:
            existing_bridges = {
                tuple(map(str, path["node_ids"][1:-1]))
                for path in selected
                if path.get("claim_safe") and len(path.get("node_ids", [])) >= 3
            }
            for candidate in candidate_paths[strict_limit:]:
                node_ids = candidate.get("node_ids", [])
                if not candidate.get("claim_safe") or len(node_ids) < 3:
                    continue
                bridge_id = tuple(map(str, node_ids[1:-1]))
                if bridge_id in existing_bridges:
                    continue
                replacement_index = next(
                    (
                        index
                        for index in range(len(selected) - 1, -1, -1)
                        if selected[index].get("gate_tier") == "C"
                    ),
                    None,
                )
                if replacement_index is None:
                    replacement_index = next(
                        (
                            index
                            for index in range(len(selected) - 1, -1, -1)
                            if selected[index].get("gate_tier") == "B"
                        ),
                        None,
                    )
                if replacement_index is None:
                    break
                selected[replacement_index] = candidate
                diversity_ids.add(id(candidate))
                existing_bridges.add(bridge_id)
                if len(diversity_ids) >= diversity_limit:
                    break
            selected.sort(key=lambda path: int(path.get("candidate_rank", 0) or 0))

        for path in selected:
            path["rescue_triggered"] = rescue_triggered
            path["rescue_added"] = rescue_triggered and path["candidate_rank"] > strict_limit
            path["rescue_outcome"] = rescue_outcome
            path["diversity_added"] = id(path) in diversity_ids
        return selected, rescue_triggered, rescue_outcome

    def _build_structured_path_entry(self, path_record: dict, candidate_rank: int) -> dict:
        """Build the auditable path payload shared by strict and rescue candidates."""
        path = path_record["path"]
        is_comm = self.graph.graph.get("num_communities", 0) > 0
        suffix = "_comm" if is_comm else ""
        names = [self.graph.nodes[node_id].get("name", node_id) for node_id in path]
        stable_ids = [generate_stable_id(f"node_{node_id}{suffix}") for node_id in path]
        edge_supports = []
        for index in range(len(path) - 1):
            u, v = path[index], path[index + 1]
            support = (
                self._select_edge_support(
                    self.graph.edges[u, v], self.claim_confidence_threshold
                )
                if self.graph.has_edge(u, v)
                else self._empty_edge_support()
            )
            edge_supports.append(support)

        gate = self._classify_path_gate(path, edge_supports, path_record["anchor_features"])
        return {
            "path": stable_ids,
            "node_ids": list(path),
            "names": names,
            "node_aliases": [
                sorted(
                    str(alias)
                    for alias in (self.graph.nodes[node_id].get("aliases", set()) or set())
                    if alias
                )
                for node_id in path
            ],
            "relations": [support["selected_relation"] for support in edge_supports],
            "edge_pmids": [
                [support["selected_pmid"]] if support["selected_pmid"] else []
                for support in edge_supports
            ],
            "edge_is_directional": [support["directional"] for support in edge_supports],
            "edge_evidence_quotes": [
                [support["selected_quote"]] if support["selected_quote"] else []
                for support in edge_supports
            ],
            "edge_evidence_complete": [
                support["support_tier"] == "A" for support in edge_supports
            ],
            "edge_supports": edge_supports,
            "score": round(path_record["score"], 3),
            "base_score": round(path_record["base_score"], 3),
            "anchor_bonus": round(path_record["anchor_bonus"], 3),
            "anchor_features": path_record["anchor_features"],
            "candidate_rank": candidate_rank,
            **gate,
            "hop_count": len(path) - 1,
        }

    def _is_valid_node(self, node_id: str) -> bool:
        """Check if node should be included based on Ontology Filtering."""
        node_data = self.graph.nodes.get(node_id, {})
        n_type = str(node_data.get("type", "entity")).lower()

        if n_type == "species" and self._is_viral_pathogen_node(node_id, node_data):
            return True
        if n_type in self.IGNORED_NODE_TYPES:
            return False

        # If we have a strict whitelist, check it
        if self.VALID_NODE_TYPES and n_type not in self.VALID_NODE_TYPES:
            return False

        return True

    @staticmethod
    def _is_viral_pathogen_node(node_id: str, node_data: dict) -> bool:
        """Retain viral pathogen entities without reopening general Species noise."""
        values = {
            str(node_data.get("name", "")),
            *map(str, node_data.get("aliases", set()) or set()),
        }
        for value in values:
            normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())
            if "virus" in normalized.split() or "viral" in normalized.split():
                return True
            compact = normalized.replace(" ", "")
            # Common biomedical virus abbreviations end in V. Requiring an
            # all-alphanumeric 3-6 character token avoids admitting organism
            # names or generic words that merely contain the letter v.
            if 3 <= len(compact) <= 6 and compact.endswith("v") and compact.isalnum():
                return True
        return False

    def score_edge_components(
        self,
        u: str,
        v: str,
        edge_data: dict,
        max_edge_weight: float,
        semantic_relevance_map: dict[str, float],
    ) -> dict[str, float]:
        """Score a single edge and expose the raw sub-components (npmi, calibrated confidence,
        query relevance) alongside the final blended score, instead of only the final float.

        This is the single source of truth for edge scoring -- `_extract_top_k_paths`'s
        `calculate_score` closure calls this and keeps only `final_score`, so there is no
        duplicated scoring logic to drift out of sync. Exposed as a public method (rather than
        staying a private closure) so calibration tooling can call it directly on arbitrary
        (u, v, edge_data) triples without re-deriving max_edge_weight/semantic_relevance_map
        traversal state itself.
        """
        # 1. Topological Evidence (NPMI) - 30%
        npmi = edge_data.get("edge_weight", 0) / max_edge_weight

        # 2. Semantic Extraction Confidence - 40%
        # Calibrate confidence based on relation strength and evidence frequency
        confidence_values = []
        for by_relation in (edge_data.get("confidences", {}) or {}).values():
            if not isinstance(by_relation, dict):
                continue
            for value in by_relation.values():
                try:
                    confidence_values.append(float(value))
                except (TypeError, ValueError):
                    continue
        # Semantic graph edges store confidence as
        # {pmid: {relation_type: score}}, not as a scalar `confidence` attribute.
        # Falling back to 0.5 preserves co-mention/BioREx behavior when no semantic score
        # exists, while semantic edges now use their actual mean extraction confidence.
        raw_conf = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else float(edge_data.get("confidence", 0.5))
        )

        # Relation Strength: Directional/Mechanistic relations are more valuable than generic associations
        rel_types = set()
        pmid_count = 0
        if "relations" in edge_data:
            rels_obj = edge_data["relations"]
            if isinstance(rels_obj, dict):
                pmid_count = len(rels_obj)
                for pmid_rels in rels_obj.values():
                    if isinstance(pmid_rels, (list, set)):
                        rel_types.update(pmid_rels)
                    elif pmid_rels:
                        rel_types.add(pmid_rels)
            elif isinstance(rels_obj, (list, set)):
                pmid_count = len(edge_data.get("pmids", [])) or 1
                rel_types.update(rels_obj)

        strength_mult = 1.0
        if any(is_directional_relation(t) for t in rel_types):
            strength_mult = 1.1  # Mechanistic boost
        elif any(t in ("associated_with", "related_to", "co_occurs_with") for t in rel_types):
            strength_mult = 0.9  # Weak association penalty

        # Evidence Frequency: More papers supporting the edge increases its trustworthiness
        evidence_boost = min(1.2, 1.0 + (max(0, pmid_count - 1) * 0.05))

        calibrated_conf = float(raw_conf) * strength_mult * evidence_boost
        calibrated_conf = min(1.0, calibrated_conf)  # Cap at 1.0

        # 3. Query Relevance (Semantic proximity to user question) - 30%
        u_rel = semantic_relevance_map.get(u, 0.5)
        v_rel = semantic_relevance_map.get(v, 0.5)
        rel_score = max(u_rel, v_rel)

        base_score = (float(npmi) * 0.3) + (float(calibrated_conf) * 0.4) + (float(rel_score) * 0.3)

        # 4. Ontology Weighting (Gene/Disease Boost)
        u_type = str(self.graph.nodes[u].get("type", "")).lower()
        v_type = str(self.graph.nodes[v].get("type", "")).lower()
        ontology_multiplier = max(
            self.TYPE_WEIGHTS.get(u_type, 1.0), self.TYPE_WEIGHTS.get(v_type, 1.0)
        )

        return {
            "npmi": float(npmi),
            "raw_conf": float(raw_conf),
            "strength_mult": strength_mult,
            "evidence_boost": evidence_boost,
            "calibrated_conf": calibrated_conf,
            "rel_score": float(rel_score),
            "base_score": base_score,
            "ontology_multiplier": ontology_multiplier,
            "final_score": base_score * ontology_multiplier,
        }

    @staticmethod
    def _normalize_anchor_text(value: object) -> str:
        """Normalize entity/query text while retaining non-Latin biomedical names."""
        normalized_value = str(value).casefold()
        for source, target in GraphRetriever.MULTILINGUAL_QUERY_ALIASES:
            normalized_value = normalized_value.replace(source, target)
        tokens = re.sub(r"[^\w]+", " ", normalized_value).split()
        normalized_tokens = []
        for token in tokens:
            # Conservative plural folding covers disease(s), mechanism(s), and
            # cell type(s), while protecting common biomedical/grammar endings.
            protected = ("ss", "us", "is", "ous", "ics", "osis")
            if (
                len(token) > 4
                and token.endswith("s")
                and not token.endswith(protected)
                and token not in {"does", "has", "this", "versus"}
            ):
                token = token[:-1]
            normalized_tokens.append(token)
        return " ".join(normalized_tokens)

    @classmethod
    def _endpoint_lexically_compatible(
        cls, phrase: str, node_id: str, node_data: dict
    ) -> bool:
        """Reject semantically nearby nodes that do not denote the endpoint.

        Vector similarity is useful for ontology variants (for example,
        ``mitochondrial dysfunction`` versus ``mitochondrial disease``), but by
        itself can silently substitute a sibling outcome such as pyroptosis for
        apoptosis.  Require a shared informative token, compact exact form, or
        an acronym match before a semantic hit may fill an explicit endpoint.
        """
        normalized_phrase = cls._normalize_anchor_text(phrase)
        phrase_tokens = set(normalized_phrase.split())
        stopwords = {
            "a", "an", "and", "by", "event", "effect", "from", "in", "of",
            "on", "or", "the", "to", "with", "blockade", "deficiency",
        }
        informative_phrase_tokens = {
            token for token in phrase_tokens if len(token) >= 3 and token not in stopwords
        }
        acronym_stopwords = {"a", "an", "and", "by", "from", "in", "of", "on", "or", "the", "to", "with"}
        acronym = "".join(
            token[0]
            for token in normalized_phrase.split()
            if token and token not in acronym_stopwords
        )
        values = {
            str(node_id),
            str(node_data.get("name", "")),
            *map(str, node_data.get("aliases", set()) or set()),
        }
        for value in values:
            normalized_value = cls._normalize_anchor_text(value)
            if not normalized_value:
                continue
            compact_value = normalized_value.replace(" ", "")
            if compact_value == normalized_phrase.replace(" ", ""):
                return True
            value_tokens = set(normalized_value.split())
            if informative_phrase_tokens & value_tokens:
                return True
            if len(acronym) >= 3 and compact_value == acronym:
                return True
        return False

    def _extract_query_anchors(
        self,
        query: str | None,
        semantic_relevance_map: dict[str, float],
        semantic_source_ids: set[str] | None = None,
        semantic_target_ids: set[str] | None = None,
    ) -> dict:
        """Extract deterministic source, target, mechanism, and context anchors."""
        normalized_query = self._normalize_anchor_text(query or "")
        padded_query = f" {normalized_query} "
        compact_query = normalized_query.replace(" ", "")
        exact_matches = []

        for node_id, node_data in self.graph.nodes(data=True):
            aliases = {str(node_id), str(node_data.get("name", ""))}
            raw_aliases = node_data.get("aliases", set()) or set()
            if isinstance(raw_aliases, str):
                raw_aliases = {raw_aliases}
            aliases.update(str(alias) for alias in raw_aliases if alias)
            positions = []
            for alias in aliases:
                normalized_alias = self._normalize_anchor_text(alias)
                if not normalized_alias:
                    continue
                position = padded_query.find(f" {normalized_alias} ")
                compact_alias = normalized_alias.replace(" ", "")
                # Gene symbols frequently differ only by punctuation or an
                # isoform suffix (IL-17 vs IL17A). Restrict compact-prefix
                # matching to aliases containing digits to avoid broad words.
                if position < 0 and any(char.isdigit() for char in compact_alias):
                    compact_stem = compact_alias
                    if compact_stem[-1:].isalpha() and compact_stem[-2:-1].isdigit():
                        compact_stem = compact_stem[:-1]
                    for candidate in (compact_alias, compact_stem):
                        if len(candidate) >= 4 and candidate in compact_query:
                            position = compact_query.find(candidate)
                            break
                if position >= 0:
                    positions.append((position, -len(normalized_alias)))
            if positions:
                position, negative_length = min(positions)
                exact_matches.append((position, negative_length, node_id))

        exact_matches.sort(key=lambda item: (item[0], item[1], str(item[2])))
        # Prefer a complete biomedical phrase over a different node matching
        # only a nested generic fragment (for example, "hepatocellular
        # carcinoma" over "carcinoma", or "chronic HBV infection" over
        # "infection"). Identical spans remain grouped as aliases.
        longest_span_matches = []
        for position, negative_length, node_id in exact_matches:
            length = -negative_length
            end = position + length
            nested_in_longer = any(
                other_position <= position
                and other_position + (-other_negative_length) >= end
                and (-other_negative_length) > length
                for other_position, other_negative_length, _ in exact_matches
            )
            if not nested_in_longer:
                longest_span_matches.append((position, negative_length, node_id))
        exact_matches = longest_span_matches

        # Multiple graph nodes can represent the same biomedical entity (for
        # example, species-specific CFTR IDs or duplicate ontology IDs).  Keep
        # every node that matched the same query span in one endpoint group so
        # a path is not rejected merely because it uses a different canonical
        # ID than the first one encountered.
        exact_match_groups = []
        for position, negative_length, node_id in exact_matches:
            group_key = (position, negative_length)
            if not exact_match_groups or exact_match_groups[-1][0] != group_key:
                exact_match_groups.append((group_key, []))
            exact_match_groups[-1][1].append(node_id)

        exact_ids = []
        for _, _, node_id in exact_matches:
            if node_id not in exact_ids:
                exact_ids.append(node_id)

        mechanism_cues = (
            "how",
            "why",
            "mechanism",
            "pathway",
            "mediate",
            "mediated",
            "via",
            "through",
            "effect of",
            "如何",
            "為何",
            "机制",
            "機制",
            "透過",
            "經由",
            "路徑",
            "中介",
        )
        mechanism_requested = any(cue in normalized_query for cue in mechanism_cues)
        negative_mechanism_requested = any(
            cue in normalized_query
            for cue in (
                "inhibit",
                "suppress",
                "reduce",
                "decrease",
                "block",
                "prevent",
                "protect",
                "抑制",
                "降低",
                "阻斷",
                "保護",
            )
        )

        # An entity explicitly introduced by "via/through/透過/經由" is a bridge
        # candidate and should not be mistaken for the question's target endpoint.
        mechanism_ids = set()
        contextual_ids = set()
        for position, negative_length, node_id in exact_matches:
            prefix = padded_query[:position].rstrip()
            match_end = position + (-negative_length) + 2
            suffix = padded_query[match_end:].lstrip()
            if re.search(r"(?:via|through|mediated by|透過|經由)\s*$", prefix) or re.match(
                r"^(?:mediated|中介)", suffix
            ):
                mechanism_ids.add(node_id)

            # A trailing population/model phrase such as "in cancer cells" or
            # "among patients" constrains the question but is not the target
            # of the requested source-to-target relation.
            if re.search(r"(?:\bin|\bwithin|\bamong)\s*$", prefix):
                contextual_ids.add(node_id)

        # Generic miRNA wording denotes a mechanism family rather than one
        # literal node name. Expand it deterministically to miR-number nodes.
        if "mirna" in compact_query or "microrna" in compact_query:
            for node_id, node_data in self.graph.nodes(data=True):
                node_name = self._normalize_anchor_text(node_data.get("name", node_id))
                compact_name = node_name.replace(" ", "")
                if re.match(r"^(?:mir|microrna)\d", compact_name):
                    mechanism_ids.add(node_id)

        endpoint_groups = []
        for _, group_ids in exact_match_groups:
            endpoint_group = [
                node_id
                for node_id in group_ids
                if node_id not in mechanism_ids and node_id not in contextual_ids
            ]
            if endpoint_group:
                endpoint_groups.append(endpoint_group)

        source_ids = set()
        target_ids = set()
        if len(endpoint_groups) >= 2:
            if " between " in padded_query or "之間" in normalized_query:
                for endpoint_group in endpoint_groups:
                    source_ids.update(endpoint_group)
                    target_ids.update(endpoint_group)
            else:
                source_ids.update(endpoint_groups[0])
                target_ids.update(endpoint_groups[-1])
        elif endpoint_groups:
            source_ids.update(endpoint_groups[0])

        endpoint_phrases = self._extract_endpoint_phrases(query)
        if endpoint_phrases:
            source_phrase, target_phrase = endpoint_phrases

            def phrase_matches(phrase: str) -> set[str]:
                normalized_phrase = self._normalize_anchor_text(phrase)
                padded_phrase = f" {normalized_phrase} "
                phrase_tokens = set(normalized_phrase.split())
                exact_matches: list[tuple[int, str]] = []
                token_matches: list[tuple[int, str]] = []
                for candidate_id, candidate_data in self.graph.nodes(data=True):
                    values = {
                        str(candidate_data.get("name", "")),
                        *map(str, candidate_data.get("aliases", set()) or set()),
                    }
                    for value in values:
                        normalized = self._normalize_anchor_text(value)
                        if not normalized:
                            continue
                        if f" {normalized} " in padded_phrase:
                            exact_matches.append((len(normalized), candidate_id))
                        candidate_tokens = set(normalized.split())
                        sufficiently_specific = len(candidate_tokens) >= 2 or (
                            len(candidate_tokens) == 1
                            and len(next(iter(candidate_tokens))) >= 5
                        )
                        if sufficiently_specific and candidate_tokens <= phrase_tokens:
                            token_matches.append((len(candidate_tokens), candidate_id))
                selected = set()
                if exact_matches:
                    longest = max(length for length, _candidate_id in exact_matches)
                    selected.update(
                        candidate_id
                        for length, candidate_id in exact_matches
                        if length == longest
                    )
                if token_matches:
                    most_tokens = max(count for count, _candidate_id in token_matches)
                    selected.update(
                        candidate_id
                        for count, candidate_id in token_matches
                        if count == most_tokens
                    )
                return {
                    candidate_id
                    for candidate_id in selected
                    if candidate_id not in mechanism_ids
                }

            phrase_source_ids = phrase_matches(source_phrase) - mechanism_ids
            phrase_target_ids = phrase_matches(target_phrase) - mechanism_ids
            # Once an explicit bridge grammar is recognized, positional
            # matches from the whole question must not leak between roles. A
            # generic word inside the source phrase (for example "infection"
            # in "chronic HBV infection") is not a target merely because the
            # true target uses a different ontology word order.
            source_ids = phrase_source_ids
            target_ids = phrase_target_ids

        if not target_ids and source_ids and mechanism_ids:
            target_ids.update(mechanism_ids)
        if not source_ids and semantic_source_ids:
            source_ids.update(
                node_id for node_id in semantic_source_ids if node_id in self.graph
            )
        if not target_ids and semantic_target_ids:
            target_ids.update(
                node_id
                for node_id in semantic_target_ids
                if node_id in self.graph and node_id not in source_ids
            )

        semantic_ids = {
            node_id
            for node_id, score in semantic_relevance_map.items()
            if node_id in self.graph and float(score) >= 0.6
        }
        return {
            "source_ids": source_ids,
            "target_ids": target_ids,
            "mechanism_ids": mechanism_ids,
            "context_ids": set(exact_ids) | semantic_ids | mechanism_ids | contextual_ids,
            "contextual_ids": contextual_ids,
            "semantic_ids": semantic_ids,
            "mechanism_requested": mechanism_requested,
            "negative_mechanism_requested": negative_mechanism_requested,
            "explicit_endpoint_query": endpoint_phrases is not None,
            "unresolved_source_endpoint": bool(endpoint_phrases and not source_ids),
            "unresolved_target_endpoint": bool(endpoint_phrases and not target_ids),
            "semantic_endpoint_fallback": bool(
                semantic_source_ids or semantic_target_ids
            ),
        }

    @classmethod
    def _extract_endpoint_phrases(cls, query: str | None) -> tuple[str, str] | None:
        """Extract explicit source/target phrases from common bridge questions."""
        normalized = cls._normalize_anchor_text(query or "")
        patterns = (
            r"\bconnect(?:s|ed|ing)?\s+(.+?)\s+to\s+(.+)$",
            r"\blink(?:s|ed|ing)?\s+(.+?)\s+to\s+(.+)$",
            r"\bbetween\s+(.+?)\s+and\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                return match.group(1).strip(), match.group(2).strip()
        match = re.search(r"連結\s*(.+?)\s*(?:與|和|到)\s*(.+)$", normalized)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None

    def _score_path_anchors(self, path: list[str], anchors: dict) -> tuple[float, dict]:
        """Return a bounded query-anchor bonus and auditable path features."""
        start_matches = bool(path and path[0] in anchors["source_ids"])
        end_matches = bool(path and path[-1] in anchors["target_ids"])
        bridge_matches = False
        if len(path) >= 3:
            bridges = path[1:-1]
            bridge_matches = any(
                bridge in anchors["mechanism_ids"] or bridge in anchors["semantic_ids"]
                for bridge in bridges
            )
            if not bridge_matches and anchors["mechanism_requested"]:
                supports = [
                    self._select_edge_support(
                        self.graph.edges[path[i], path[i + 1]],
                        self.claim_confidence_threshold,
                    )
                    for i in range(len(path) - 1)
                ]
                bridge_matches = any(support["directional"] for support in supports)

        spans_multiple = (start_matches and end_matches) or (
            bridge_matches and (start_matches or end_matches)
        )

        # A lone source match is common to every path traversed from that source,
        # so it is exposed as a feature but does not inflate absolute edge scores.
        bonus = 0.0
        if end_matches:
            bonus += 0.04
        if bridge_matches:
            bonus += 0.04
        if spans_multiple:
            bonus += 0.04
        bonus = min(0.12, bonus)

        features = {
            "source_anchor_ids": sorted(str(node_id) for node_id in anchors["source_ids"]),
            "target_anchor_ids": sorted(str(node_id) for node_id in anchors["target_ids"]),
            "mechanism_anchor_ids": sorted(
                str(node_id) for node_id in anchors["mechanism_ids"]
            ),
            "context_anchor_ids": sorted(str(node_id) for node_id in anchors["context_ids"]),
            "mechanism_requested": anchors["mechanism_requested"],
            "negative_mechanism_requested": anchors.get(
                "negative_mechanism_requested", False
            ),
            "explicit_endpoint_query": anchors.get("explicit_endpoint_query", False),
            "unresolved_source_endpoint": anchors.get(
                "unresolved_source_endpoint", False
            ),
            "unresolved_target_endpoint": anchors.get(
                "unresolved_target_endpoint", False
            ),
            "start_matches_query_focus": start_matches,
            "end_matches_query_focus": end_matches,
            "bridge_matches_mechanism_context": bridge_matches,
            "path_spans_multiple_anchor_types": spans_multiple,
        }
        return bonus, features

    def _classify_path_gate(
        self, path: list[str], edge_supports: list[dict], anchor_features: dict
    ) -> dict:
        """Classify a path as claim-safe (A), retrieval-only (B), or discard (C)."""
        reasons = []
        if not edge_supports or any(support["support_tier"] == "C" for support in edge_supports):
            return {
                "gate_tier": "C",
                "gate_reasons": ["missing_relation_support"],
                "claim_safe": False,
                "retrieval_safe": False,
            }

        direction_contradicted = False
        for index, support in enumerate(edge_supports):
            if not support["directional"]:
                continue
            edge_data = self.graph.edges[path[index], path[index + 1]]
            source_id = edge_data.get("source_id")
            if source_id is not None and str(source_id) != str(path[index]):
                direction_contradicted = True
                reasons.append(f"direction_contradicted_hop_{index + 1}")

        source_anchors = anchor_features.get("source_anchor_ids", [])
        target_anchors = anchor_features.get("target_anchor_ids", [])
        context_anchors = set(anchor_features.get("context_anchor_ids", []))
        start_matches = bool(anchor_features.get("start_matches_query_focus"))
        end_matches = bool(anchor_features.get("end_matches_query_focus"))
        if anchor_features.get("explicit_endpoint_query"):
            endpoint_aligned = bool(source_anchors and target_anchors) and (
                start_matches and end_matches
            )
            if anchor_features.get("unresolved_source_endpoint"):
                reasons.append("unresolved_source_endpoint")
            if anchor_features.get("unresolved_target_endpoint"):
                reasons.append("unresolved_target_endpoint")
        elif target_anchors:
            endpoint_aligned = start_matches and end_matches
        elif source_anchors:
            endpoint_aligned = start_matches
        elif context_anchors:
            endpoint_aligned = any(str(node_id) in context_anchors for node_id in path)
        else:
            endpoint_aligned = False
            reasons.append("query_alignment_unknown")

        reasons.append(
            "query_endpoint_alignment" if endpoint_aligned else "poor_endpoint_alignment"
        )
        every_hop_complete = all(support["support_tier"] == "A" for support in edge_supports)
        if every_hop_complete:
            reasons.append("complete_hop_evidence")
        else:
            for index, support in enumerate(edge_supports):
                if support["support_tier"] != "A":
                    reasons.append(f"incomplete_evidence_hop_{index + 1}")

        bridge_plausible = len(path) < 3 or bool(
            anchor_features.get("bridge_matches_mechanism_context")
        )
        non_composable_hops = [
            index + 1
            for index, support in enumerate(edge_supports)
            if str(support.get("selected_relation", "")).casefold()
            in self.NON_COMPOSABLE_MULTI_HOP_RELATIONS
        ]
        if len(path) >= 3 and non_composable_hops:
            bridge_plausible = False
            reasons.extend(
                f"non_composable_intervention_hop_{index}"
                for index in non_composable_hops
            )
        if len(path) > 3:
            directional_hops = sum(bool(support["directional"]) for support in edge_supports)
            negative_hops = sum(
                str(support.get("selected_relation", "")).casefold()
                in self.NEGATIVE_RELATIONS
                for support in edge_supports
            )
            evidence_pmids = {
                str(support["selected_pmid"])
                for support in edge_supports
                if support.get("selected_pmid")
            }
            bridge_plausible = not non_composable_hops and bool(
                anchor_features.get("explicit_endpoint_query")
                and anchor_features.get("mechanism_requested")
                and directional_hops >= 2
                and len(evidence_pmids) >= 2
                and len(path) <= 5
                and (
                    negative_hops % 2 == 0
                    or anchor_features.get("negative_mechanism_requested")
                )
            )
            if negative_hops % 2 and not anchor_features.get(
                "negative_mechanism_requested"
            ):
                reasons.append("unresolved_path_polarity")
            reasons.append(
                "bounded_mechanistic_multi_hop"
                if bridge_plausible
                else "weak_long_path_mechanism"
            )
        elif len(path) == 3:
            reasons.append("plausible_bridge" if bridge_plausible else "weak_bridge_alignment")

        if direction_contradicted:
            tier = "C"
        elif every_hop_complete and endpoint_aligned and bridge_plausible:
            tier = "A"
        elif endpoint_aligned or not (source_anchors or target_anchors or context_anchors):
            tier = "B"
        else:
            tier = "C"

        return {
            "gate_tier": tier,
            "gate_reasons": reasons,
            "claim_safe": tier == "A",
            "retrieval_safe": tier in {"A", "B"},
        }

    def _extract_top_k_paths(
        self,
        start_nodes: list[str],
        query: str | None,
        max_hops: int,
        top_k: int,
        include_anchor_details: bool = False,
    ) -> list:
        """Traverse, evidence-score, anchor-rerank, and return the top graph paths.

        The default return shape remains ``[(path, score)]`` for compatibility.
        Internal callers can request records containing base score and anchor
        diagnostics for structured evaluation output.
        """
        all_paths = []

        # Pre-compute maximum edge weight for normalization across the requested subnetwork
        max_edge_weight = 1e-6
        for _, _, data in self.graph.edges(data=True):
            w = data.get("edge_weight", 0)
            if w > max_edge_weight:
                max_edge_weight = w

        # Strategy 2.0: Fetch node semantic relevance to the actual user query
        semantic_relevance_map = {}
        semantic_source_ids: set[str] = set()
        semantic_target_ids: set[str] = set()
        if query and self.node_rag:
            logger.info(f"Scoring 2-hop graph relevance for query: {query}")
            # Search for more nodes to ensure we cover the 2-hop neighborhood
            hits = self.node_rag.search_nodes(query, top_k=100)
            semantic_relevance_map = {node_id: score for node_id, score, _ in hits}

            endpoint_phrases = self._extract_endpoint_phrases(query)
            if endpoint_phrases:
                source_phrase, target_phrase = endpoint_phrases

                def best_endpoint_ids(phrase: str) -> set[str]:
                    endpoint_hits = self.node_rag.search_nodes(phrase, top_k=5)
                    endpoint_hits = [
                        hit
                        for hit in endpoint_hits
                        if hit[0] in self.graph
                        and self._endpoint_lexically_compatible(
                            phrase, hit[0], self.graph.nodes[hit[0]]
                        )
                    ]
                    if not endpoint_hits or float(endpoint_hits[0][1]) < 0.5:
                        return set()
                    best_score = float(endpoint_hits[0][1])
                    return {
                        node_id
                        for node_id, score, _meta in endpoint_hits
                        if float(score) >= best_score - 0.03
                    }

                semantic_source_ids = best_endpoint_ids(source_phrase)
                semantic_target_ids = best_endpoint_ids(target_phrase)

        anchors = self._extract_query_anchors(
            query,
            semantic_relevance_map,
            semantic_source_ids=semantic_source_ids,
            semantic_target_ids=semantic_target_ids,
        )

        def calculate_score(u, v, edge_data):
            return self.score_edge_components(
                u, v, edge_data, max_edge_weight, semantic_relevance_map
            )["final_score"]

        # Cap start nodes to prevent O(n²) traversal on large graphs
        MAX_START_NODES = 50
        if len(start_nodes) > MAX_START_NODES:
            # Sort start nodes by query relevance so the most query-relevant nodes are prioritized as start nodes
            if query:
                query_lower = query.lower()

                def get_start_node_priority(node_id):
                    node_data = self.graph.nodes.get(node_id, {})
                    name = str(node_data.get("name", "")).lower().strip()

                    # 1. Substring match of node name/label in query
                    in_query = 0.0
                    if name and name in query_lower:
                        in_query = 2.0
                    elif name:
                        words = [w for w in name.split() if len(w) > 2]
                        if words and any(w in query_lower for w in words):
                            in_query = 1.0

                    # 2. Semantic relevance score
                    sem_score = semantic_relevance_map.get(node_id, 0.0)

                    # 3. Graph degree (as a tie breaker)
                    deg = self.graph.degree(node_id) if self.graph.has_node(node_id) else 0
                    deg_score = min(0.1, deg / 1000.0)

                    return in_query + sem_score + deg_score

                start_nodes = sorted(start_nodes, key=get_start_node_priority, reverse=True)
            else:
                # If no query, sort by degree descending
                start_nodes = sorted(
                    start_nodes,
                    key=lambda n: self.graph.degree(n) if self.graph.has_node(n) else 0,
                    reverse=True,
                )

            # Keep only the top MAX_START_NODES that have edges
            start_nodes = [n for n in start_nodes if self.graph.degree(n) > 0][:MAX_START_NODES]

        visited_paths = set()

        for start_node in start_nodes:
            # 1-hop — sorted() ensures deterministic traversal order
            for neighbor in sorted(self.graph.neighbors(start_node)):
                if neighbor == start_node:
                    continue
                if not self._is_valid_node(neighbor):
                    continue

                edge_1 = self.graph[start_node][neighbor]
                score_1 = calculate_score(start_node, neighbor, edge_1)

                # Use a DIRECTED signature so (A→B) and (B→A) are kept separately.
                # An undirected edge storing "inhibits" may mean A inhibits B when
                # explored from A, and B inhibits A when explored from B; keeping
                # both lets the LLM see the biologically correct direction.
                path_sig_1 = (start_node, neighbor)
                if path_sig_1 not in visited_paths:
                    path_1 = [start_node, neighbor]
                    anchor_bonus, anchor_features = self._score_path_anchors(path_1, anchors)
                    all_paths.append(
                        {
                            "path": path_1,
                            "score": score_1 + anchor_bonus,
                            "base_score": score_1,
                            "anchor_bonus": anchor_bonus,
                            "anchor_features": anchor_features,
                        }
                    )
                    visited_paths.add(path_sig_1)

                if max_hops >= 2:
                    # 2-hop — sorted() ensures deterministic traversal order
                    for n2 in sorted(self.graph.neighbors(neighbor)):
                        if n2 == start_node or n2 == neighbor:
                            continue
                        if not self._is_valid_node(n2):
                            continue

                        edge_2 = self.graph[neighbor][n2]
                        score_2 = calculate_score(neighbor, n2, edge_2)

                        # Strategy: Reduce False Inferences
                        # Use 'Bottleneck Scoring' (Min-Link) instead of Average.
                        # Also apply a 0.8x penalty for the 2-hop jump to acknowledge increased uncertainty.
                        path_score = min(score_1, score_2) * 0.8

                        # Use a directed-aware sig for 2-hop to distinguish start->mid->end
                        path_sig_2 = (start_node, neighbor, n2)
                        if path_sig_2 not in visited_paths:
                            path_2 = list(path_sig_2)
                            anchor_bonus, anchor_features = self._score_path_anchors(
                                path_2, anchors
                            )
                            all_paths.append(
                                {
                                    "path": path_2,
                                    "score": path_score + anchor_bonus,
                                    "base_score": path_score,
                                    "anchor_bonus": anchor_bonus,
                                    "anchor_features": anchor_features,
                                }
                            )
                            visited_paths.add(path_sig_2)

        # For explicit endpoint mechanism questions, search only between the
        # resolved endpoints when a bounded path longer than two hops is
        # requested. This avoids expanding every node neighborhood while still
        # recovering cross-document mechanisms that intrinsically need three
        # or four edges.
        endpoint_paths = []
        if max_hops > 2 and anchors.get("explicit_endpoint_query"):
            for source_id in sorted(anchors["source_ids"], key=str):
                for target_id in sorted(anchors["target_ids"], key=str):
                    if source_id == target_id:
                        continue
                    try:
                        candidates = nx.all_simple_paths(
                            self.graph, source_id, target_id, cutoff=min(max_hops, 4)
                        )
                        for path in islice(candidates, 5000):
                            if len(path) <= 3 or tuple(path) in visited_paths:
                                continue
                            if any(not self._is_valid_node(node_id) for node_id in path[1:-1]):
                                continue
                            edge_scores = [
                                calculate_score(path[i], path[i + 1], self.graph[path[i]][path[i + 1]])
                                for i in range(len(path) - 1)
                            ]
                            hop_count = len(path) - 1
                            base_score = min(edge_scores) * (0.8 ** (hop_count - 1))
                            anchor_bonus, anchor_features = self._score_path_anchors(path, anchors)
                            endpoint_paths.append(
                                {
                                    "path": list(path),
                                    "score": base_score + anchor_bonus,
                                    "base_score": base_score,
                                    "anchor_bonus": anchor_bonus,
                                    "anchor_features": anchor_features,
                                }
                            )
                            visited_paths.add(tuple(path))
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue
            all_paths.extend(endpoint_paths)

        # Sort paths by score descending; use path tuple as tie-breaker for determinism
        all_paths.sort(key=lambda item: (-item["score"], tuple(item["path"])))
        selected_paths = all_paths[:top_k]
        if max_hops > 2 and endpoint_paths:
            # Global edge scoring favors short, frequent relations. Preserve a
            # very small tail of fully evidenced endpoint-to-endpoint paths so
            # they reach the strict gate instead of being truncated before
            # evidence and direction can be assessed.
            selected_signatures = {tuple(item["path"]) for item in selected_paths}
            endpoint_tail = []
            qualified_endpoint_paths = []
            for item in endpoint_paths:
                path = item["path"]
                if len(path) <= 3 or tuple(path) in selected_signatures:
                    continue
                features = item.get("anchor_features", {})
                if not (
                    features.get("start_matches_query_focus")
                    and features.get("end_matches_query_focus")
                ):
                    continue
                supports = [
                    self._select_edge_support(
                        self.graph.edges[path[i], path[i + 1]],
                        self.claim_confidence_threshold,
                    )
                    for i in range(len(path) - 1)
                ]
                if not all(support["support_tier"] == "A" for support in supports):
                    continue
                direction_ok = all(
                    not support["directional"]
                    or self.graph.edges[path[index], path[index + 1]].get("source_id") is None
                    or str(self.graph.edges[path[index], path[index + 1]].get("source_id"))
                    == str(path[index])
                    for index, support in enumerate(supports)
                )
                if not direction_ok:
                    continue
                directional_hops = sum(bool(support["directional"]) for support in supports)
                evidence_pmids = {
                    str(support["selected_pmid"])
                    for support in supports
                    if support.get("selected_pmid")
                }
                qualified_endpoint_paths.append(
                    (directional_hops, len(evidence_pmids), item)
                )
            qualified_endpoint_paths.sort(
                key=lambda record: (
                    -record[0],
                    -record[1],
                    -record[2]["score"],
                    tuple(record[2]["path"]),
                )
            )
            for _directional_hops, _evidence_count, item in qualified_endpoint_paths:
                path = item["path"]
                endpoint_tail.append(item)
                selected_signatures.add(tuple(path))
                if len(endpoint_tail) >= 20:
                    break
            selected_paths.extend(endpoint_tail)
        if include_anchor_details:
            return selected_paths
        return [(item["path"], item["score"]) for item in selected_paths]

    def _format_path(self, path: list[str]) -> str:
        """Format a node sequence path into a readable string.

        Edges are annotated with [DIRECTIONAL] or [SYMMETRIC] so the LLM
        can immediately determine whether a path qualifies for Layer 3
        (Causal Biomedical Mechanism) reasoning. Stored evidence quotes are
        included so downstream generation can validate the relation instead
        of receiving an unauditable edge label alone.
        """
        descriptions = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            u_name = self.graph.nodes[u].get("name", u)
            v_name = self.graph.nodes[v].get("name", v)
            edge_data = self.graph[u][v]
            support = self._select_edge_support(
                edge_data, self.claim_confidence_threshold
            )
            directionality = "[DIRECTIONAL]" if support["directional"] else "[SYMMETRIC]"
            pmid = (
                f" [PMID:{support['selected_pmid']}]" if support["selected_pmid"] else ""
            )
            relations = f"{support['selected_relation']} {directionality}{pmid}"
            description = f"{u_name} --[{relations}]--> {v_name}"
            evidence = self._format_edge_evidence(edge_data)
            if evidence:
                description += f' {{EVIDENCE: "{evidence}"}}'
            if support["conflicting_evidence"]:
                conflict_str = " vs ".join(
                    f"PMID:{c['pmid']} {c['relation']}({c['polarity']})"
                    for c in support["conflicting_evidence"]
                )
                description += f" {{CONFLICT: {conflict_str}}}"
            descriptions.append(description)

        return " | ".join(descriptions)

    @staticmethod
    def _empty_edge_support() -> dict:
        """Return the stable schema used when an expected graph edge is absent."""
        return {
            "selected_relation": "associated_with",
            "selected_pmid": None,
            "selected_quote": None,
            "selected_confidence": None,
            "directional": False,
            "support_tier": "C",
            "support_reasons": ["no_relation_support"],
            "conflicting_evidence": [],
        }

    @staticmethod
    def _detect_polarity_conflict(candidates: list[dict]) -> list[dict]:
        """Find PMIDs that report opposite regulatory direction for the same edge.

        ``_select_edge_support`` collapses every (PMID, relation) candidate down to
        one "winner" for the prompt, which previously made contradictory literature
        (e.g. one paper says A inhibits B, another says A activates B) invisible to
        the LLM -- it only ever saw the winning side. Surfacing the conflict here
        lets Layer 3 report it explicitly instead of silently picking one side.
        """
        polarity_by_pmid: dict[str, str] = {}
        for candidate in candidates:
            polarity = relation_polarity(candidate["selected_relation"])
            if polarity is None:
                continue
            pmid = candidate["selected_pmid"]
            if pmid is None:
                continue
            # A PMID may support multiple relations for the same edge; keep the
            # first unambiguous polarity seen for it rather than overwriting.
            polarity_by_pmid.setdefault(pmid, polarity)

        distinct_polarities = set(polarity_by_pmid.values())
        if len(distinct_polarities) < 2:
            return []

        conflicts = []
        for candidate in candidates:
            pmid = candidate["selected_pmid"]
            polarity = polarity_by_pmid.get(pmid)
            if polarity is None:
                continue
            conflicts.append(
                {
                    "pmid": pmid,
                    "relation": candidate["selected_relation"],
                    "polarity": polarity,
                }
            )
        # Deterministic order: sorted by PMID so output doesn't depend on dict/set iteration order.
        return sorted(conflicts, key=lambda item: (item["pmid"], item["relation"]))

    @staticmethod
    def _iter_edge_support_candidates(edge_data: dict) -> list[dict]:
        """Join relation, quote, and confidence maps at ``(PMID, relation)`` level.

        Graphs created by older import paths may contain only one or two of the
        three maps. Taking their union keeps those edges visible while making
        incompleteness explicit in ``support_tier`` and ``support_reasons``.
        """
        relations_map = edge_data.get("relations", {}) or {}
        evidence_map = edge_data.get("evidences", {}) or {}
        confidence_map = edge_data.get("confidences", {}) or {}
        mechanism_event_map = edge_data.get("mechanism_events", {}) or {}
        normalized_evidence_map = {
            str(pmid): {str(relation): value for relation, value in by_relation.items()}
            for pmid, by_relation in evidence_map.items()
            if isinstance(by_relation, dict)
        }
        normalized_confidence_map = {
            str(pmid): {str(relation): value for relation, value in by_relation.items()}
            for pmid, by_relation in confidence_map.items()
            if isinstance(by_relation, dict)
        }
        normalized_event_map = {
            str(pmid): {str(relation): value for relation, value in by_relation.items()}
            for pmid, by_relation in mechanism_event_map.items()
            if isinstance(by_relation, dict)
        }
        candidate_keys = set()

        for mapping in (relations_map, evidence_map, confidence_map):
            if not isinstance(mapping, dict):
                continue
            for pmid, values in mapping.items():
                if isinstance(values, dict):
                    candidate_keys.update((str(pmid), str(relation)) for relation in values)
                elif isinstance(values, (set, list, tuple)):
                    candidate_keys.update((str(pmid), str(relation)) for relation in values)
                elif isinstance(values, str) and mapping is relations_map:
                    candidate_keys.add((str(pmid), values))

        candidates = []
        for pmid, relation in sorted(candidate_keys):
            by_evidence = normalized_evidence_map.get(pmid, {})
            by_confidence = normalized_confidence_map.get(pmid, {})
            raw_quote = by_evidence.get(relation)
            quote = " ".join(str(raw_quote or "").split()) or None
            raw_confidence = by_confidence.get(relation)
            try:
                confidence = float(raw_confidence) if raw_confidence is not None else None
            except (TypeError, ValueError):
                confidence = None

            candidate = {
                    "selected_relation": relation,
                    "selected_pmid": pmid,
                    "selected_quote": quote,
                    "selected_confidence": confidence,
                    "directional": is_directional_relation(relation),
                    "quote_relation_aligned": bool(quote)
                    and relation_supported_by_text(quote, relation),
                }
            mechanism_event = normalized_event_map.get(pmid, {}).get(relation)
            if mechanism_event is not None:
                candidate["selected_mechanism_event"] = mechanism_event
            candidates.append(candidate)
        return candidates

    @classmethod
    def _select_edge_support(
        cls,
        edge_data: dict,
        claim_confidence_threshold: float = DEFAULT_CLAIM_CONFIDENCE_THRESHOLD,
    ) -> dict:
        """Select one deterministic, internally aligned evidence bundle for an edge."""
        candidates = cls._iter_edge_support_candidates(edge_data)
        if not candidates:
            return cls._empty_edge_support()

        def selection_key(candidate: dict) -> tuple:
            confidence = candidate["selected_confidence"]
            return (
                1 if candidate["quote_relation_aligned"] else 0,
                1 if candidate["selected_quote"] else 0,
                1 if confidence is not None else 0,
                1 if candidate["directional"] else 0,
                confidence if confidence is not None else -1.0,
            )

        # Candidates are lexically sorted, and max() retains the first item on
        # ties. This provides a deterministic PMID/relation tie-break without
        # allowing arbitrary insertion order to influence the result.
        selected = dict(max(candidates, key=selection_key))
        reasons = []
        if selected["selected_quote"]:
            reasons.append("quote_present")
        else:
            reasons.append("quote_missing")
        threshold = float(claim_confidence_threshold)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("claim_confidence_threshold must be between 0 and 1")
        if selected["selected_confidence"] is not None:
            reasons.append("confidence_present")
            if selected["selected_confidence"] >= threshold:
                reasons.append(f"confidence_ge_{threshold:g}")
            else:
                reasons.append(f"confidence_below_{threshold:g}")
        else:
            reasons.append("confidence_missing")
        if selected["directional"]:
            reasons.append("directional_relation")
        else:
            reasons.append("symmetric_relation")
        reasons.append(
            "quote_relation_aligned"
            if selected["quote_relation_aligned"]
            else "quote_relation_mismatch"
        )

        # Tier A is safe for later claim-gate consideration. Tier B remains
        # useful retrieval context but lacks a quote or calibrated confidence.
        selected["support_tier"] = (
            "A"
            if selected["selected_quote"]
            and selected["selected_confidence"] is not None
            and selected["selected_confidence"] >= threshold
            and selected["quote_relation_aligned"]
            else "B"
        )
        selected["support_reasons"] = reasons
        selected["conflicting_evidence"] = cls._detect_polarity_conflict(candidates)
        return selected

    @classmethod
    def _format_edge_evidence(cls, edge_data: dict, max_chars: int = 320) -> str:
        """Return the canonical PMID-linked quote for an edge prompt payload."""
        support = cls._select_edge_support(edge_data)
        if not support["selected_quote"]:
            return ""
        confidence = support["selected_confidence"]
        confidence_text = f"; confidence={confidence:.3f}" if confidence is not None else ""
        return (
            f"PMID:{support['selected_pmid']}; relation={support['selected_relation']}"
            f"{confidence_text}; quote={support['selected_quote'][:max_chars]}"
        )

    def _summarize_relations(self, edge_data: dict) -> str:
        """Summarize relation types in an edge with supporting PMIDs.

        Appends [DIRECTIONAL] for mechanistic relations (inhibits, activates,
        etc.) and [SYMMETRIC] for co-occurrence/association edges.  This gives
        the downstream LLM an unambiguous signal for Layer 3 eligibility.
        """
        all_types = set()
        pmids = set()

        if "relations" in edge_data:
            for pmid, pmid_relations in edge_data["relations"].items():
                all_types.update(pmid_relations)
                pmids.add(pmid)

        if not all_types:
            type_str = "associated"
            directionality = "[SYMMETRIC]"
        else:
            sorted_types = sorted(all_types)
            type_str = ", ".join(sorted_types[:3])
            # Determine directionality based on primary relation type
            primary = Counter(sorted_types).most_common(1)[0][0] if sorted_types else "associated"
            directionality = "[DIRECTIONAL]" if is_directional_relation(primary) else "[SYMMETRIC]"

        # Add PMIDs
        if pmids:
            # Sort for deterministic output and limit to top 3
            sorted_pmids = sorted(pmids)[:3]
            pmid_str = ", ".join([f"PMID:{p}" for p in sorted_pmids])
            return f"{type_str} {directionality} [{pmid_str}]"

        return f"{type_str} {directionality}"
