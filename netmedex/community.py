from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class GraphCommunity:
    """Represents a topological functional community in the biomedical knowledge graph."""

    community_id: int
    title: str
    summary: str
    node_count: int
    edge_count: int
    top_hubs: list[str] = field(default_factory=list)
    gene_hubs: list[str] = field(default_factory=list)
    drug_hubs: list[str] = field(default_factory=list)
    disease_hubs: list[str] = field(default_factory=list)
    phenotype_hubs: list[str] = field(default_factory=list)
    top_pmids: list[str] = field(default_factory=list)
    key_relations: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphCommunity:
        return cls(**data)


class CommunityDetector:
    """
    Detects, analyzes, and manages topological communities for Macro-Level GraphRAG.
    """

    def __init__(self, graph: nx.Graph, seed: int = 42):
        self.graph = graph
        self.seed = seed
        self.communities: list[GraphCommunity] = []
        self._node_to_community_map: dict[str, int] = {}

    def build_communities(
        self,
        min_community_size: int = 2,
        max_hubs_per_type: int = 5,
    ) -> list[GraphCommunity]:
        """
        Partition graph nodes into communities using the Louvain algorithm and compute metadata.
        """
        if len(self.graph.nodes) == 0:
            self.communities = []
            self._node_to_community_map = {}
            return []

        # Filter out existing meta/community nodes
        subgraph_nodes = [
            n
            for n, d in self.graph.nodes(data=True)
            if d.get("type") != "community" and not str(n).startswith("c_meta_")
        ]
        if not subgraph_nodes:
            return []

        subgraph = self.graph.subgraph(subgraph_nodes)

        # Detect communities using Louvain modularity optimization
        try:
            raw_communities = nx.community.louvain_communities(
                subgraph, weight="edge_weight", seed=self.seed
            )
        except Exception as e:
            logger.warning("Louvain community detection failed, falling back to connected components: %s", e)
            raw_communities = list(nx.connected_components(subgraph))

        # Sort communities by size descending
        raw_communities = sorted(raw_communities, key=len, reverse=True)

        communities: list[GraphCommunity] = []
        self._node_to_community_map = {}

        for c_idx, node_set in enumerate(raw_communities):
            if len(node_set) < min_community_size and len(raw_communities) > 1:
                # Keep small communities only if it's the only one or sufficiently informative
                continue

            c_subgraph = subgraph.subgraph(node_set)
            node_count = c_subgraph.number_of_nodes()
            edge_count = c_subgraph.number_of_edges()

            # Rank nodes by weighted degree within the community
            node_degrees = dict(c_subgraph.degree(weight="edge_weight"))
            ranked_nodes = sorted(node_degrees.keys(), key=lambda n: node_degrees[n], reverse=True)

            top_hubs: list[str] = []
            gene_hubs: list[str] = []
            drug_hubs: list[str] = []
            disease_hubs: list[str] = []
            phenotype_hubs: list[str] = []

            for n in ranked_nodes:
                node_data = self.graph.nodes[n]
                name = str(node_data.get("name") or n)
                ntype = str(node_data.get("type", "")).lower()

                if len(top_hubs) < max_hubs_per_type * 2 and name not in top_hubs:
                    top_hubs.append(name)

                if ntype == "gene" and len(gene_hubs) < max_hubs_per_type and name not in gene_hubs:
                    gene_hubs.append(name)
                elif (
                    ntype in ("chemical", "drug")
                    and len(drug_hubs) < max_hubs_per_type
                    and name not in drug_hubs
                ):
                    drug_hubs.append(name)
                elif (
                    ntype == "disease"
                    and len(disease_hubs) < max_hubs_per_type
                    and name not in disease_hubs
                ):
                    disease_hubs.append(name)
                elif (
                    ntype in ("phenotype", "biologicalprocess", "pathway")
                    and len(phenotype_hubs) < max_hubs_per_type
                    and name not in phenotype_hubs
                ):
                    phenotype_hubs.append(name)

                self._node_to_community_map[str(n)] = c_idx

            # Collect top PMIDs and relations
            pmid_counter: Counter[str] = Counter()
            relation_counter: Counter[str] = Counter()

            for u, v, data in c_subgraph.edges(data=True):
                pmids = data.get("pmids") or []
                if isinstance(pmids, (list, set)):
                    for p in pmids:
                        if p:
                            pmid_counter[str(p)] += 1
                elif pmids:
                    pmid_counter[str(pmids)] += 1

                relations = data.get("relations") or []
                if isinstance(relations, list):
                    for r in relations:
                        if r:
                            relation_counter[str(r)] += 1
                elif data.get("relation_type"):
                    relation_counter[str(data["relation_type"])] += 1

            top_pmids = [p for p, _ in pmid_counter.most_common(5)]
            key_relations = [r for r, _ in relation_counter.most_common(4)]

            # Generate descriptive title and summary
            title = self._generate_title(c_idx, top_hubs, gene_hubs, disease_hubs, drug_hubs)
            summary = self._generate_summary(
                node_count,
                edge_count,
                gene_hubs,
                disease_hubs,
                drug_hubs,
                phenotype_hubs,
                key_relations,
            )

            comm = GraphCommunity(
                community_id=c_idx,
                title=title,
                summary=summary,
                node_count=node_count,
                edge_count=edge_count,
                top_hubs=top_hubs[:6],
                gene_hubs=gene_hubs,
                drug_hubs=drug_hubs,
                disease_hubs=disease_hubs,
                phenotype_hubs=phenotype_hubs,
                top_pmids=top_pmids,
                key_relations=key_relations,
                node_ids=[str(n) for n in node_set],
            )
            communities.append(comm)

        self.communities = communities
        return communities

    def _generate_title(
        self,
        c_idx: int,
        top_hubs: list[str],
        gene_hubs: list[str],
        disease_hubs: list[str],
        drug_hubs: list[str],
    ) -> str:
        """Create a semantic title for the community."""
        key_entities = []
        if disease_hubs:
            key_entities.append(disease_hubs[0])
        if gene_hubs:
            key_entities.append(gene_hubs[0])
        elif drug_hubs:
            key_entities.append(drug_hubs[0])
        elif top_hubs:
            key_entities.append(top_hubs[0])

        if key_entities:
            entity_str = " / ".join(key_entities)
            return f"Community #{c_idx}: {entity_str} Functional Axis"
        return f"Community #{c_idx}: Module ({len(top_hubs)} Hubs)"

    def _generate_summary(
        self,
        node_count: int,
        edge_count: int,
        gene_hubs: list[str],
        disease_hubs: list[str],
        drug_hubs: list[str],
        phenotype_hubs: list[str],
        key_relations: list[str],
    ) -> str:
        """Generate a natural language overview of the functional community."""
        parts = [f"Functional cluster comprising {node_count} entities and {edge_count} interactions."]

        elements = []
        if gene_hubs:
            elements.append(f"Genes ({', '.join(gene_hubs)})")
        if disease_hubs:
            elements.append(f"Diseases ({', '.join(disease_hubs)})")
        if drug_hubs:
            elements.append(f"Chemicals/Drugs ({', '.join(drug_hubs)})")
        if phenotype_hubs:
            elements.append(f"Phenotypes/Pathways ({', '.join(phenotype_hubs)})")

        if elements:
            parts.append(f"Primary components: {'; '.join(elements)}.")

        if key_relations:
            parts.append(f"Predominant interaction mechanisms: {', '.join(key_relations)}.")

        return " ".join(parts)

    def match_communities(
        self,
        query: str,
        matched_node_ids: list[str] | None = None,
        top_k: int = 2,
    ) -> list[tuple[GraphCommunity, float]]:
        """
        Match the most relevant macro-level communities for a given user query.

        Scoring logic:
        - Query keywords in Title: +3.0
        - Query keywords in Hub names: +2.0
        - Matched node IDs belonging to the community: +2.5
        - Query keywords in Summary: +1.0
        """
        if not self.communities:
            self.build_communities()

        if not self.communities:
            return []

        query_lower = query.lower()
        query_tokens = set(query_lower.replace("-", " ").replace("_", " ").split())

        matched_set = set(matched_node_ids or [])
        scored_communities: list[tuple[GraphCommunity, float]] = []

        for comm in self.communities:
            score = 0.0

            # 1. Title keyword matching
            title_lower = comm.title.lower()
            for token in query_tokens:
                if len(token) > 2 and token in title_lower:
                    score += 3.0

            # 2. Hub names matching
            all_hubs = set(
                h.lower()
                for h in comm.top_hubs
                + comm.gene_hubs
                + comm.drug_hubs
                + comm.disease_hubs
                + comm.phenotype_hubs
            )
            for token in query_tokens:
                if len(token) > 2:
                    for hub in all_hubs:
                        if token in hub:
                            score += 2.0
                            break

            # 3. Direct node membership matching
            if matched_set:
                overlap = len(matched_set.intersection(comm.node_ids))
                score += overlap * 2.5

            # 4. Summary keyword matching
            summary_lower = comm.summary.lower()
            for token in query_tokens:
                if len(token) > 3 and token in summary_lower:
                    score += 1.0

            if score > 0.0:
                scored_communities.append((comm, score))

        # Sort by relevance score descending
        scored_communities.sort(key=lambda x: x[1], reverse=True)

        if not scored_communities and self.communities:
            # Return largest communities as fallback with score 0.5
            return [(c, 0.5) for c in self.communities[:top_k]]

        return scored_communities[:top_k]

    def save_to_json(self, filepath: str | Path) -> None:
        """Save detected communities to a JSON file."""
        data = [c.to_dict() for c in self.communities]
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_from_json(self, filepath: str | Path) -> list[GraphCommunity]:
        """Load communities from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.communities = [GraphCommunity.from_dict(item) for item in data]
        self._node_to_community_map = {}
        for comm in self.communities:
            for n in comm.node_ids:
                self._node_to_community_map[str(n)] = comm.community_id
        return self.communities
