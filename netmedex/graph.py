import importlib
import logging
import math
import pickle
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from operator import itemgetter
from pathlib import Path
from typing import Literal

import networkx as nx

from netmedex.graph_data import (
    NODE_COLOR_MAP,
    NODE_SHAPE_MAP,
    CommunityEdge,
    GraphEdge,
    GraphNode,
)
from netmedex.headers import HEADERS
from netmedex.npmi import normalized_pointwise_mutual_information
from netmedex.pubtator_data import (
    PubTatorArticle,
    PubTatorCollection,
    PubTatorRelation,
    PubTatorRelationParser,
)
from netmedex.pubtator_graph_data import (
    PubTatorEdge,
    PubTatorNode,
    PubTatorNodeCollection,
)
from netmedex.utils import generate_uuid

MIN_EDGE_WIDTH = 0
MAX_EDGE_WIDTH = 20


logger = logging.getLogger(__name__)


class PubTatorGraphBuilder:
    """Constructs a co-mention or BioREx relation network from PubTator3 articles.

    Call `add_article` or `add_collection` to ingest articles, then invoke
    and `build` once all articles have been added.

    A NetworkX `Graph` is maintained incrementally:

    * **Nodes** (`GraphNode`)
      * color/shape reflect semantic type (gene, disease, chemical, ...)
      * `pmids` stores every PubMed ID in which the concept appears
      * attributes such as `num_articles`, `weighted_num_articles`,
        community assignment (`parent`), and layout position (`pos`)
        are filled during `build`.
    * **Edges** (`GraphEdge`)
      * `relations` is a mapping `{pmid: {"co-mention", "Inhibits", ...}}`
      * statistical weights (frequency or NPMI) are calculated in `build`.
    * **Graph-level attributes**
      * `graph.graph["pmid_title"]` - `{pmid: title}`
      * `graph.graph["num_communities"]` - set after community detection.

    The typical workflow is:

    ```python
    builder = PubTatorGraphBuilder(node_type="all")
    builder.add_collection(collection)           # or builder.add_article(...)
    G = builder.build(
        pmid_weights={"12345678": 2.0},          # optional importance
        weighting_method="npmi",                 # or "freq"
        edge_weight_cutoff=2,                    # prune weak links (max weight = 20)
        community=True,                          # Louvain clustering
        max_edges=500                            # keep top-500 edges
    )
    ```

    Args:
        node_type (Literal["all", "mesh", "relation"]):
            Determines which annotations become nodes and which
            edges are created.
            * `"all"` - every PubTator annotation becomes a node and
              both co-mention and explicit-relation edges are added.
            * `"mesh"` - only MeSH terms become nodes; edge creation
              behaves like `"all"`.
            * `"relation"` - only MeSH terms appear as nodes *and*
              **only** BioREx-annotated relations are added as edges.
              Co-mention edges are skipped.
    """

    node_type: Literal["all", "mesh", "relation"]
    num_articles: int
    _mesh_only: bool
    graph: nx.Graph
    _updated: bool
    """Track whether any new articles are added"""

    def __init__(
        self,
        node_type: Literal["all", "mesh", "relation"],
    ) -> None:
        self.node_type = node_type
        self._mesh_only = node_type in ("mesh", "relation")
        self.num_articles = 0
        self.graph = nx.Graph()
        self._updated = False
        self._init_graph_attributes()

    def add_collection(
        self,
        collection: PubTatorCollection,
    ):
        use_mesh_vocabulary = HEADERS["use_mesh_vocabulary"] in collection.headers
        for article in collection.articles:
            self.add_article(article, use_mesh_vocabulary=use_mesh_vocabulary)

    def add_article(
        self,
        article: PubTatorArticle,
        use_mesh_vocabulary: bool = True,
    ):
        self._updated = True
        self.num_articles += 1

        node_collection = PubTatorNodeCollection(
            mesh_only=self._mesh_only, use_mesh_vocabulary=use_mesh_vocabulary
        )
        for annotation in article.annotations:
            node_collection.add_node(annotation)

        edges = []
        if self.node_type != "relation":
            edges += self._create_complete_graph_edges(
                list(node_collection.nodes.keys()), article.pmid
            )

        edges += self._create_relation_edges(
            list(node_collection.mesh_nodes.keys()), article.relations
        )

        self._add_attributes(article)
        self._add_nodes(node_collection.nodes)
        self._add_edges(edges)

    def build(
        self,
        pmid_weights: dict[str, int | float] | None = None,
        weighting_method: Literal["freq", "npmi"] = "freq",
        edge_weight_cutoff: int = 0,
        community: bool = True,
        max_edges: int = 0,
    ):
        """Build the co-mention network with edge weights

        Args:
            pmid_weights (dict[str, int | float], optional):
                The weight (importance) of each article.
            weighting_method (Literal["freq", "npmi"], optional):
                Method used for calculating edge weights. Defaults to "freq".
            edge_weight_cutoff (int, optional):
                For removing edges with weights below the cutoff. Defaults to 0.
            community (bool, optional):
                Whether to apply the community detection method. Defaults to True.
            max_edges (int, optional):
                For keep top [max_edges] edges sorted descendingly by edge weights. Defaults to 0.
        """

        self._build_nodes(pmid_weights)
        self._build_edges(pmid_weights, weighting_method)

        self._remove_edges_by_weight(self.graph, edge_weight_cutoff)
        self._remove_edges_by_rank(self.graph, max_edges)

        self._remove_isolated_nodes(self.graph)

        self._check_graph_properties(self.graph)

        self._set_network_layout(self.graph)

        if community:
            self._set_network_communities(self.graph)

        self._log_graph_info()
        self._updated = False

        return self.graph

    def _build_nodes(self, pmid_weights: dict[str, int | float] | None = None):
        for _, data in self.graph.nodes(data=True):
            data["num_articles"] = len(data["pmids"])
            if pmid_weights is not None:
                data["weighted_num_articles"] = round(
                    sum([pmid_weights.get(pmid, 1) for pmid in data["pmids"]]), 2
                )
            else:
                data["weighted_num_articles"] = data["num_articles"]

    def _build_edges(
        self,
        pmid_weights: dict[str, int | float] | None,
        weighting_method: Literal["npmi", "freq"],
    ):
        # Update attributes for edges
        for u, v, data in self.graph.edges(data=True):
            data["num_relations"] = len(data["relations"])
            if pmid_weights is not None:
                data["weighted_num_relations"] = round(
                    sum([pmid_weights.get(pmid, 1) for pmid in data["relations"]]), 2
                )
            else:
                data["weighted_num_relations"] = data["num_relations"]

            # data["num_relations_doc_weighted"] = num_evidence *
            data["npmi"] = normalized_pointwise_mutual_information(
                n_x=self.graph.nodes[u]["weighted_num_articles"],
                n_y=self.graph.nodes[v]["weighted_num_articles"],
                n_xy=data["weighted_num_relations"],
                N=self.num_articles,
                n_threshold=2,
            )

        # Calculate scaled weights
        if weighting_method == "npmi":
            edge_weights: dict[tuple[str, str], float] = nx.get_edge_attributes(self.graph, "npmi")
            scale_factor = MAX_EDGE_WIDTH
        elif weighting_method == "freq":
            edge_weights: dict[tuple[str, str], float] = nx.get_edge_attributes(
                self.graph, "weighted_num_relations"
            )
            max_weight = max(edge_weights.values())

            # This only scales down the width. If # supporting relations is
            # smaller than MAX_EDGE_WIDTH, the edge width will equal the weight
            scale_factor = min(MAX_EDGE_WIDTH / max_weight, 1)

        # Update scaled weights for edges
        for edge, weight in edge_weights.items():
            scaled_weight = round(max(weight * scale_factor, 0.0), 2)
            self.graph.edges[edge].update(
                {
                    "edge_weight": scaled_weight,
                    "edge_width": max(scaled_weight, MIN_EDGE_WIDTH),
                }
            )

    @staticmethod
    def _remove_edges_by_weight(graph: nx.Graph, edge_weight_cutoff: int | float):
        to_remove = []
        for u, v, edge_attrs in graph.edges(data=True):
            if edge_attrs["edge_width"] < edge_weight_cutoff:
                to_remove.append((u, v))
        graph.remove_edges_from(to_remove)

    @staticmethod
    def _remove_edges_by_rank(graph: nx.Graph, max_edges: int):
        if max_edges <= 0:
            return

        if graph.number_of_edges() > max_edges:
            edges = sorted(
                # u, v, data
                graph.edges(data=True),
                key=lambda x: x[2]["edge_weight"],
                reverse=True,
            )
            for edge in edges[max_edges:]:
                graph.remove_edge(edge[0], edge[1])

    @staticmethod
    def _remove_isolated_nodes(graph: nx.Graph):
        graph.remove_nodes_from(list(nx.isolates(graph)))

    @staticmethod
    def _check_graph_properties(graph: nx.Graph):
        num_selfloops = nx.number_of_selfloops(graph)
        if num_selfloops != 0:
            logger.warning(f"[Error] Find {num_selfloops} selfloops")

    @staticmethod
    def _set_network_layout(graph: nx.Graph):
        if graph.number_of_edges() > 1000:
            pos = nx.circular_layout(graph, scale=300)
        else:
            pos = nx.spring_layout(graph, weight="edge_weight", scale=300, k=0.25, iterations=15)
        nx.set_node_attributes(graph, pos, "pos")

    @staticmethod
    def _set_network_communities(graph: nx.Graph, seed: int = 1):
        communities = nx.community.louvain_communities(graph, seed=seed, weight="edge_weight")  # type: ignore
        community_labels = set()
        for c_idx, community in enumerate(communities):
            highest_degree_node = max(
                graph.degree(community, weight="edge_weight"),  # type: ignore
                key=itemgetter(1),
            )[0]
            community_node = f"c{c_idx}"
            community_labels.add(community_node)
            community_attrs = graph.nodes[highest_degree_node].copy()
            community_attrs.update(
                {"label_color": "#dd4444", "parent": None, "_id": community_node}
            )
            node_data = GraphNode(**community_attrs)
            graph.add_node(community_node, **asdict(node_data))

            for node in community:
                graph.nodes[node]["parent"] = community_node

        graph.graph["num_communities"] = len(community_labels)

        # Gather edges between communities
        inter_edge_weight = defaultdict(float)
        inter_edge_pmids = defaultdict(dict)
        to_remove = []
        for u, v, attrs in graph.edges(data=True):
            if (c_0 := graph.nodes[u]["parent"]) != (c_1 := graph.nodes[v]["parent"]):
                if c_0 is None or c_1 is None:
                    logger.warning(f"[Error] Node {u} or {v} is not in any community")
                    continue
                to_remove.append((u, v))
                community_edge = tuple(sorted([c_0, c_1]))
                inter_edge_weight[community_edge] += attrs["edge_weight"]
                inter_edge_pmids[community_edge].update(attrs["relations"])

        graph.remove_edges_from(to_remove)
        for (c_0, c_1), weight in inter_edge_weight.items():
            # Log-adjusted weight for balance
            try:
                weight = math.log(weight) * 5
                weight = 0.0 if weight < 0.0 else weight
            except ValueError:
                weight = 0.0
            pmids = set(inter_edge_pmids[(c_0, c_1)])
            edge_data = CommunityEdge(
                _id=generate_uuid(),
                type="community",
                edge_weight=weight,
                edge_width=max(weight, MIN_EDGE_WIDTH),
                pmids=set(pmids),
            )
            graph.add_edge(c_0, c_1, **asdict(edge_data))

    def _log_graph_info(self):
        logger.info(f"# articles: {len(self.graph.graph['pmid_title'])}")
        if num_communities := self.graph.graph.get("num_communities", 0):
            logger.info(f"# communities: {num_communities}")
        logger.info(f"# nodes: {self.graph.number_of_nodes() - num_communities}")
        logger.info(f"# edges: {self.graph.number_of_edges()}")

    def _create_complete_graph_edges(
        self, node_ids: Sequence[str], pmid: str
    ) -> list[PubTatorEdge]:
        """Build co-mention edges for all given nodes

        Assuming that all nodes are in the same article.
        """
        edges: list[PubTatorEdge] = []
        for i in range(len(node_ids) - 1):
            for j in range(i + 1, len(node_ids)):
                # Node1 and Node2 always follow alphabetical order
                if node_ids[i] <= node_ids[j]:
                    edge = PubTatorEdge(node_ids[i], node_ids[j], pmid, "co-mention")
                else:
                    edge = PubTatorEdge(node_ids[j], node_ids[i], pmid, "co-mention")
                edges.append(edge)

        return edges

    def _create_relation_edges(
        self,
        mesh_node_ids: Sequence[str],
        relations: Sequence[PubTatorRelation],
    ) -> list[PubTatorEdge]:
        """Only create BioREx annotated edges"""
        parser = PubTatorRelationParser(mesh_node_ids)

        edges = []
        for relation in relations:
            if (node_ids := parser.parse(relation)) is None:
                continue
            else:
                edges.append(
                    PubTatorEdge(node_ids[0], node_ids[1], relation.pmid, relation.relation_type)
                )

        return edges

    def _add_nodes(self, nodes: Mapping[str, PubTatorNode]):
        for node_id, data in nodes.items():
            if self.graph.has_node(node_id):
                self.graph.nodes[node_id]["pmids"].add(data.pmid)
            else:
                node_data = GraphNode(
                    _id=generate_uuid(),
                    color=NODE_COLOR_MAP[data.type],
                    label_color="#000000",
                    shape=NODE_SHAPE_MAP[data.type],
                    type=data.type,
                    mesh=data.mesh,
                    name=data.name,
                    pmids={data.pmid},
                    num_articles=None,
                    weighted_num_articles=None,
                    marked=False,
                    parent=None,
                    pos=None,
                )
                self.graph.add_node(node_id, **asdict(node_data))

    def _add_edges(self, edges: Sequence[PubTatorEdge]):
        for edge in edges:
            if self.graph.has_edge(edge.node1_id, edge.node2_id):
                relation_dict: dict[str, set[str]] = self.graph.edges[
                    edge.node1_id, edge.node2_id
                ]["relations"]

                if relation_dict.get(edge.pmid) is None:
                    relation_dict[edge.pmid] = {edge.relation}
                else:
                    relation_dict[edge.pmid].add(edge.relation)
            else:
                edge_data = GraphEdge(
                    _id=generate_uuid(),
                    type="node",
                    relations={edge.pmid: {edge.relation}},
                    num_relations=None,
                    weighted_num_relations=None,
                    npmi=None,
                    edge_weight=None,
                    edge_width=None,
                )
                self.graph.add_edge(edge.node1_id, edge.node2_id, **asdict(edge_data))

    def _add_attributes(self, article: PubTatorArticle):
        # Add pmid_title as a graph attribute
        self.graph.graph["pmid_title"][article.pmid] = article.title

    def _init_graph_attributes(self):
        self.graph.graph["pmid_title"] = {}


def save_graph(
    G: nx.Graph,
    savepath: str | Path,
    output_filetype: Literal["xgmml", "html", "json", "pickle"],
):
    format_function_map = {
        "xgmml": "netmedex.cytoscape_xgmml.save_as_xgmml",
        "html": "netmedex.cytoscape_js.save_as_html",
        "json": "netmedex.cytoscape_js.save_as_json",
    }
    if output_filetype == "pickle":
        with open(savepath, "wb") as f:
            pickle.dump(G, f)
    else:
        module_path, func_name = format_function_map[output_filetype].rsplit(".", 1)
        module = importlib.import_module(module_path)
        save_func = getattr(module, func_name)
        save_func(G, savepath)

    logger.info(f"Save graph to {savepath}")


def load_graph(graph_pickle_path: str):
    with open(graph_pickle_path, "rb") as f:
        G = pickle.load(f)

    return G
