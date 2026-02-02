from __future__ import annotations

import logging
import networkx as nx

logger = logging.getLogger(__name__)


class GraphRetriever:
    """
    Retrieves structured context from the knowledge graph for Hybrid RAG.
    """

    def __init__(self, graph: nx.Graph):
        """
        Initialize the Graph Retriever.

        Args:
            graph: The NetworkX graph containing the knowledge network.
        """
        self.graph = graph
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

        Current strategy: Simple substring matching against indexed names.

        Args:
            query: User's natural language query.

        Returns:
            List of unique node IDs found in the query.
        """
        query_lower = query.lower()
        matched_nodes = set()

        # Check for direct presence of known entity names in the query
        # This is a basic entity linking approach.
        # Optimization: Sort names by length (descending) to match longest phrases first
        sorted_names = sorted(self.name_to_id.keys(), key=len, reverse=True)

        for name in sorted_names:
            if name in query_lower:
                # Basic boundary check could be improved (e.g., regex)
                matched_nodes.add(self.name_to_id[name])

        return list(matched_nodes)

    def get_subgraph_context(self, relevant_nodes: list[str], max_hops: int = 2) -> str:
        """
        Extract textual context describing the subgraph relevant to the nodes.

        Strategy:
        1. If 1 node: Return 1-hop neighbors.
        2. If 2+ nodes: Find shortest paths between them to reveal connections.

        Args:
            relevant_nodes: List of starting node IDs.
            max_hops: Maximum number of hops for pathfinding.

        Returns:
            Formatted string describing the structural relationships.
        """
        if not relevant_nodes:
            return "No specific entities from the graph were found in the query."

        # Filter nodes to ensure they exist in the current graph
        # (graph might have changed or passed subgraphs might be disjoint)
        valid_nodes = [n for n in relevant_nodes if self.graph.has_node(n)]

        if not valid_nodes:
            return "Identified entities are not present in the current subnetwork."

        context_lines = []

        # Case 1: Single Node Analysis - Show immediate context
        if len(valid_nodes) == 1:
            start_node = valid_nodes[0]
            start_data = self.graph.nodes[start_node]
            start_name = start_data.get("name", start_node)
            start_type = start_data.get("type", "Entity")

            context_lines.append(f"Entity: {start_name} ({start_type})")

            neighbors = list(self.graph.neighbors(start_node))
            if not neighbors:
                context_lines.append(f"- {start_name} has no connections in this view.")
            else:
                context_lines.append(f"- Direct connections ({len(neighbors)}):")
                # Sort neighbors by edge weight if available
                scored_neighbors = []
                for n in neighbors:
                    edge = self.graph[start_node][n]
                    weight = edge.get("edge_weight", 0)
                    scored_neighbors.append((n, weight))

                scored_neighbors.sort(key=lambda x: x[1], reverse=True)

                for n, weight in scored_neighbors[:10]:  # Limit to top 10
                    n_data = self.graph.nodes[n]
                    n_name = n_data.get("name", n)
                    n_type = n_data.get("type", "m")

                    # Inspect edge relations
                    edge_data = self.graph[start_node][n]
                    relations = self._summarize_relations(edge_data)

                    context_lines.append(
                        f"  * {n_name} ({n_type}) [{relations}] (Weight: {weight})"
                    )

        # Case 2: Multi-Node Analysis - Find paths
        else:
            context_lines.append(
                f"Relational analysis between: {', '.join([self.graph.nodes[n].get('name', n) for n in valid_nodes])}"
            )

            pairs_analyzed = 0
            # Compare all pairs (limit to a reasonable number to avoid combinatorial explosion)
            import itertools

            for n1, n2 in itertools.combinations(valid_nodes, 2):
                if pairs_analyzed > 5:
                    break

                path = self._find_connection(n1, n2, max_hops)
                if path:
                    context_lines.append(f"\nPath: {self._format_path(path)}")
                    pairs_analyzed += 1
                else:
                    context_lines.append(
                        f"\nNo direct connection found between {self.graph.nodes[n1].get('name', n1)} and {self.graph.nodes[n2].get('name', n2)} within {max_hops} hops."
                    )

        return "\n".join(context_lines)

    def _find_connection(self, source: str, target: str, cutoff: int) -> list[str] | None:
        """Find meaningful connection between two nodes."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return None
        except Exception:
            return None

    def _format_path(self, path: list[str]) -> str:
        """Format a node sequence path into a readable string."""
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
        """Summarize relation types in an edge with supporting PMIDs."""
        # relations is typically {pmid: {set of types}}
        all_types = set()
        pmids = set()

        if "relations" in edge_data:
            for pmid, pmid_relations in edge_data["relations"].items():
                all_types.update(pmid_relations)
                pmids.add(pmid)

        if not all_types:
            type_str = "associated"
        else:
            type_str = ", ".join(list(all_types)[:3])

        # Add PMIDs
        if pmids:
            # Sort for deterministic output and limit to top 3
            sorted_pmids = sorted(pmids)[:3]
            pmid_str = ", ".join([f"PMID:{p}" for p in sorted_pmids])
            return f"{type_str} [{pmid_str}]"

        return type_str
