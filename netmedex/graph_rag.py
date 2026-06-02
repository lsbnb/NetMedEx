from __future__ import annotations

import logging
from collections import Counter

import networkx as nx

from netmedex.relation_types import is_directional_relation
from netmedex.utils import generate_stable_id

logger = logging.getLogger(__name__)


class GraphRetriever:
    """
    Retrieves structured context from the knowledge graph for Hybrid RAG.
    """

    # Ontology Preference: Prioritize Genes and Diseases while ignoring non-biomedical noise
    VALID_NODE_TYPES = {"gene", "disease", "chemical", "variant", "pathway", "cellline"}
    IGNORED_NODE_TYPES = {"species", "entity", "geographic area", "organism"}

    TYPE_WEIGHTS = {"gene": 1.2, "disease": 1.2, "chemical": 1.1, "variant": 1.1}

    def __init__(self, graph: nx.Graph, node_rag=None):
        """
        Initialize the Graph Retriever.

        Args:
            graph: The NetworkX graph containing the knowledge network.
            node_rag: Optional NodeRAG instance for semantic search.
        """
        self.graph = graph
        self.node_rag = node_rag
        self._build_node_index()

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
        matched_nodes = set()

        # 1. Exact/Substring Matching
        sorted_names: list[str] = sorted(self.name_to_id.keys(), key=len, reverse=True)
        for name in sorted_names:
            if name in query_lower:
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
        if not relevant_nodes:
            return "No specific entities from the graph were found in the query.", []

        # Filter nodes to ensure they exist in the current graph
        valid_nodes = [n for n in relevant_nodes if self.graph.has_node(n)]

        if not valid_nodes:
            return "Identified entities are not present in the current subnetwork.", []

        context_lines = []
        structured_paths = []

        # Support robust 2-hop contextual paths using hybrid scoring and filtering
        explored_paths = self._extract_top_k_paths(
            valid_nodes, query=query, max_hops=max_hops, top_k=20
        )

        # Pre-scan all paths to determine if ANY directional (mechanistic) edges exist.
        # This flag is passed to the LLM in the header so it knows whether Layer 3
        # (Causal Biomedical Mechanism) can be triggered.
        has_directional_edges = False
        for path, _ in explored_paths:
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                if self.graph.has_edge(u, v):
                    rel_sets = self.graph.edges[u, v].get("relations", {})
                    all_rels = [r for rels in rel_sets.values() for r in rels]
                    if any(is_directional_relation(r) for r in all_rels):
                        has_directional_edges = True
                        break
            if has_directional_edges:
                break

        if not explored_paths:
            context_lines.append("[DIRECTIONAL MECHANISTIC EDGES: NO]")
            context_lines.append(
                "No significant relational paths could be found for the queried entities."
            )
        else:
            # Emit a clear header that the LLM uses to decide Layer 3 eligibility.
            dir_flag = "YES" if has_directional_edges else "NO"
            context_lines.append(f"[DIRECTIONAL MECHANISTIC EDGES: {dir_flag}]")
            context_lines.append(
                f"Latent Network Mechanisms (Top {len(explored_paths)} 2-hop paths based on Confidence+Topology+Topic):"
            )
            for path, score in explored_paths:
                context_lines.append(f"- {self._format_path(path)} (Score: {score:.2f})")

                # Build structured path entry.
                # Recompute stable Cytoscape IDs using the same logic as
                # normalize_graph_ids() so they always match element data.id /
                # data.source / data.target regardless of when _id was last written
                # to the node attributes (e.g. community-suffix mismatch).
                is_comm = self.graph.graph.get("num_communities", 0) > 0
                suffix = "_comm" if is_comm else ""
                names = [self.graph.nodes[node_id].get("name", node_id) for node_id in path]
                stable_ids = [generate_stable_id(f"node_{node_id}{suffix}") for node_id in path]
                # Collect primary relation type and PMIDs for each edge in the path
                edge_relations = []
                edge_pmids = []
                edge_is_directional = []
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]
                    if self.graph.has_edge(u, v):
                        edata = self.graph.edges[u, v]
                        rel_sets = edata.get("relations", {})
                        all_rels = [r for rels in rel_sets.values() for r in rels]
                        primary = (
                            Counter(all_rels).most_common(1)[0][0]
                            if all_rels
                            else "associated_with"
                        )
                        pmids = sorted(rel_sets.keys())[:3]
                        directional = is_directional_relation(primary)
                    else:
                        primary = "associated_with"
                        pmids = []
                        directional = False
                    edge_relations.append(primary)
                    edge_pmids.append(pmids)
                    edge_is_directional.append(directional)

                structured_paths.append(
                    {
                        "path": stable_ids,
                        "names": names,
                        "relations": edge_relations,
                        "edge_pmids": edge_pmids,
                        "edge_is_directional": edge_is_directional,
                        "score": round(score, 3),
                        "hop_count": len(path) - 1,
                    }
                )

        return "\n".join(context_lines), structured_paths

    def _is_valid_node(self, node_id: str) -> bool:
        """Check if node should be included based on Ontology Filtering."""
        node_data = self.graph.nodes.get(node_id, {})
        n_type = str(node_data.get("type", "entity")).lower()

        if n_type in self.IGNORED_NODE_TYPES:
            return False

        # If we have a strict whitelist, check it
        if self.VALID_NODE_TYPES and n_type not in self.VALID_NODE_TYPES:
            return False

        return True

    def _extract_top_k_paths(
        self, start_nodes: list[str], query: str | None, max_hops: int, top_k: int
    ) -> list[tuple[list[str], float]]:
        """Traverse 1 and 2 hops from core nodes, score paths via hybrid confidence, and return Top K."""
        all_paths = []

        # Pre-compute maximum edge weight for normalization across the requested subnetwork
        max_edge_weight = 1e-6
        for _, _, data in self.graph.edges(data=True):
            w = data.get("edge_weight", 0)
            if w > max_edge_weight:
                max_edge_weight = w

        # Strategy 2.0: Fetch node semantic relevance to the actual user query
        semantic_relevance_map = {}
        if query and self.node_rag:
            logger.info(f"Scoring 2-hop graph relevance for query: {query}")
            # Search for more nodes to ensure we cover the 2-hop neighborhood
            hits = self.node_rag.search_nodes(query, top_k=100)
            semantic_relevance_map = {node_id: score for node_id, score, _ in hits}

        def calculate_score(u, v, edge_data):
            # 1. Topological Evidence (NPMI) - 30%
            npmi = edge_data.get("edge_weight", 0) / max_edge_weight

            # 2. Semantic Extraction Confidence - 40%
            # Calibrate confidence based on relation strength and evidence frequency
            raw_conf = edge_data.get("confidence", 0.5)

            # Relation Strength: Directional/Mechanistic relations are more valuable than generic associations
            rel_types = set()
            pmid_count = 0
            if "relations" in edge_data:
                pmid_count = len(edge_data["relations"])
                for pmid_rels in edge_data["relations"].values():
                    rel_types.update(pmid_rels)

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

            base_score = (
                (float(npmi) * 0.3) + (float(calibrated_conf) * 0.4) + (float(rel_score) * 0.3)
            )

            # 4. Ontology Weighting (Gene/Disease Boost)
            u_type = str(self.graph.nodes[u].get("type", "")).lower()
            v_type = str(self.graph.nodes[v].get("type", "")).lower()
            multiplier = max(
                self.TYPE_WEIGHTS.get(u_type, 1.0), self.TYPE_WEIGHTS.get(v_type, 1.0)
            )

            return base_score * multiplier

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
            # 1-hop
            for neighbor in self.graph.neighbors(start_node):
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
                    all_paths.append(([start_node, neighbor], score_1))
                    visited_paths.add(path_sig_1)

                if max_hops >= 2:
                    # 2-hop
                    for n2 in self.graph.neighbors(neighbor):
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
                            all_paths.append((list(path_sig_2), path_score))
                            visited_paths.add(path_sig_2)

        # Sort paths by score descending
        all_paths.sort(key=lambda x: x[1], reverse=True)
        return all_paths[:top_k]

    def _format_path(self, path: list[str]) -> str:
        """Format a node sequence path into a readable string.

        Edges are annotated with [DIRECTIONAL] or [SYMMETRIC] so the LLM
        can immediately determine whether a path qualifies for Layer 3
        (Causal Biomedical Mechanism) reasoning.
        """
        descriptions = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            u_name = self.graph.nodes[u].get("name", u)
            v_name = self.graph.nodes[v].get("name", v)
            edge_data = self.graph[u][v]
            relations = self._summarize_relations(edge_data)
            descriptions.append(f"{u_name} --[{relations}]--> {v_name}")

        return " | ".join(descriptions)

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
