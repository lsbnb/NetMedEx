import csv
import importlib
import logging
import math
import pickle
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from operator import itemgetter
from typing import Literal

import networkx as nx

from netmedex.graph_data import CommunityEdgeData, GraphEdgeData, GraphNodeData
from netmedex.npmi import normalized_pointwise_mutual_information
from netmedex.pubtator_parser import (
    PubTatorParser,
    PubTatorResult,
)
from netmedex.utils import generate_uuid

# VARIANT_PATTERN = re.compile(r"CorrespondingGene:.*CorrespondingSpecies:\d+")

MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)"),
}

NODE_COLOR_MAP = {
    "Chemical": "#67A9CF",
    "Gene": "#74C476",
    "Species": "#FD8D3C",
    "Disease": "#8C96C6",
    "DNAMutation": "#FCCDE5",
    "ProteinMutation": "#FA9FB5",
    "CellLine": "#BDBDBD",
    "SNP": "#FFFFB3",
}
NODE_SHAPE_MAP = {
    "Chemical": "ELLIPSE",
    "Gene": "TRIANGLE",
    "Species": "DIAMOND",
    "Disease": "ROUNDRECTANGLE",
    "DNAMutation": "PARALLELOGRAM",
    "ProteinMutation": "HEXAGON",
    "CellLine": "VEE",
    "SNP": "OCTAGON",
}

MIN_EDGE_WIDTH = 0
MAX_EDGE_WIDTH = 20
EDGE_BASE_COLOR = "#AD1A66"

# TODO: other ways to solve modified MeSH mismatch
mesh_map = {}
logger = logging.getLogger(__name__)


class NetworkBuilder:
    def __init__(
        self,
        pubtator_filepath: str,
        savepath: str | None,
        node_type: Literal["all", "mesh", "relation"],
        output_filetype: Literal["html", "xgmml", "json"],
        weighting_method: Literal["freq", "npmi"],
        edge_weight_cutoff: int,
        pmid_weight_filepath: str | None,
        community: bool,
        max_edges: int,
        debug: bool,
    ):
        self.pubtator_filepath = pubtator_filepath
        self.savepath = savepath
        self.node_type = node_type
        self.output_filetype = output_filetype
        self.weighting_method = weighting_method
        self.edge_weight_cutoff = edge_weight_cutoff
        self.pmid_weight_filepath = pmid_weight_filepath
        self.community = community
        self.max_edges = max_edges
        self.debug = debug

    def run(self):
        self.check_not_implemented()
        G = nx.Graph()
        result = PubTatorParser(
            pubtator_filepath=self.pubtator_filepath,
            node_type=self.node_type,
        ).parse()
        self.add_node_to_graph(G=G, parsed_pubtator=result)
        self.add_edge_to_graph(G=G, parsed_pubtator=result)
        self.add_attrs_to_graph(G=G, parsed_pubtator=result)

        if self.debug:
            # Save before truncation
            now = datetime.now().strftime("%y%m%d%H%M%S")
            with open(f"tocytoscape_graph_{now}.pkl", "wb") as f:
                pickle.dump(G, f)

        self.remove_edges_by_weight(G)
        self.remove_edges_by_rank(G)

        self.remove_isolated_nodes(G)

        self.check_graph_properties(G)

        self.set_network_layout(G)

        if self.community:
            self.set_network_communities(G)

        self.log_graph_info(G, result)
        self.save_network(G)

        return G

    def check_not_implemented(self):
        if self.community and self.output_filetype == "xgmml":
            msg = "Save community in XGMML format not yet supported."
            logger.info(msg)
            raise NotImplementedError(msg)

    @staticmethod
    def add_node_to_graph(G: nx.Graph, parsed_pubtator: PubTatorResult):
        # TODO: add feature: mark specific names
        marked = False
        for node_id in parsed_pubtator.non_isolated_nodes:
            node_data = GraphNodeData(
                _id=str(parsed_pubtator.node_dict[node_id].id),
                color=NODE_COLOR_MAP[parsed_pubtator.node_dict[node_id].type],
                label_color="#000000",
                shape=NODE_SHAPE_MAP[parsed_pubtator.node_dict[node_id].type],
                type=parsed_pubtator.node_dict[node_id].type,
                name=parsed_pubtator.node_dict[node_id].name,
                document_frequency=len(parsed_pubtator.node_dict[node_id].pmids),
                marked=marked,
            )
            G.add_node(node_id, **asdict(node_data))

    def add_edge_to_graph(self, G: nx.Graph, parsed_pubtator: PubTatorResult):
        doc_weights = {}
        if self.pmid_weight_filepath is not None:
            with open(self.pmid_weight_filepath, newline="") as f:
                reader = csv.reader(f)
                for row in reader:
                    doc_weights[row[0]] = float(row[1])

        for pair, edge_data_list in parsed_pubtator.edge_dict.items():
            if not G.has_node(pair[0]) or not G.has_node(pair[1]):
                continue

            pmids = [edge_data.pmid for edge_data in edge_data_list]
            unique_pmids = set(pmids)

            w_freq = round(sum([doc_weights.get(pmid, 1) for pmid in unique_pmids]), 2)
            npmi = normalized_pointwise_mutual_information(
                n_x=len(parsed_pubtator.node_dict[pair[0]].pmids),
                n_y=len(parsed_pubtator.node_dict[pair[1]].pmids),
                n_xy=len(unique_pmids),
                N=parsed_pubtator.num_pmids,
                n_threshold=2,
                below_threshold_default=MIN_EDGE_WIDTH / MAX_EDGE_WIDTH,
            )

            if self.weighting_method == "npmi":
                edge_weight = npmi
            elif self.weighting_method == "freq":
                edge_weight = w_freq

            edge_data = GraphEdgeData(
                _id=str(edge_data_list[0].id),
                raw_frequency=len(unique_pmids),
                doc_weighted_frequency=w_freq,
                npmi=npmi,
                edge_weight=edge_weight,
                pmids=list(unique_pmids),
            )

            G.add_edge(pair[0], pair[1], type="node", **asdict(edge_data))

        edge_weights = nx.get_edge_attributes(G, "edge_weight")
        scale_factor = self._calculate_scale_factor(
            edge_weights=edge_weights.values(),
            max_width=MAX_EDGE_WIDTH,
        )
        for edge, weight in edge_weights.items():
            scaled_weight = max(weight * scale_factor, 0.0)
            G.edges[edge]["scaled_edge_weight"] = round(scaled_weight, 2)
            G.edges[edge]["edge_width"] = int(max(scaled_weight, MIN_EDGE_WIDTH))

    def _calculate_scale_factor(
        self,
        edge_weights: Sequence[float],
        max_width: int,
    ):
        max_weight = max(edge_weights)
        if self.weighting_method == "npmi":
            scale_factor = max_width
        elif self.weighting_method == "freq":
            scale_factor = min(max_width / max_weight, 1)

        return scale_factor

    def remove_edges_by_weight(self, G: nx.Graph):
        to_remove = []
        for u, v, edge_attrs in G.edges(data=True):
            if edge_attrs["edge_width"] < self.edge_weight_cutoff:
                to_remove.append((u, v))
        G.remove_edges_from(to_remove)

    def remove_edges_by_rank(self, G: nx.Graph):
        if self.max_edges <= 0:
            return

        if G.number_of_edges() > self.max_edges:
            edges = sorted(
                G.edges(data=True), key=lambda x: x[2]["scaled_edge_weight"], reverse=True
            )
            for edge in edges[self.max_edges :]:
                G.remove_edge(edge[0], edge[1])

    @staticmethod
    def remove_isolated_nodes(G: nx.Graph):
        G.remove_nodes_from(list(nx.isolates(G)))

    @staticmethod
    def add_attrs_to_graph(G: nx.Graph, parsed_pubtator: PubTatorResult):
        G.graph["pmid_title"] = parsed_pubtator.pmid_title_map

    @staticmethod
    def check_graph_properties(G: nx.Graph):
        num_selfloops = nx.number_of_selfloops(G)
        if num_selfloops != 0:
            logger.warning(f"[Error] Find {num_selfloops} selfloops")

    @staticmethod
    def set_network_layout(G: nx.Graph):
        if G.number_of_edges() > 1000:
            pos = nx.circular_layout(G, scale=300)
        else:
            pos = nx.spring_layout(
                G, weight="scaled_edge_weight", scale=300, k=0.25, iterations=15
            )
        nx.set_node_attributes(G, pos, "pos")

    @staticmethod
    def set_network_communities(G: nx.Graph, seed: int = 1):
        communities = nx.community.louvain_communities(G, seed=seed, weight="scaled_edge_weight")
        community_labels = set()
        for c_idx, community in enumerate(communities):
            highest_degree_node = max(
                G.degree(community, weight="scaled_edge_weight"), key=itemgetter(1)
            )[0]
            community_node = f"c{c_idx}"
            community_labels.add(community_node)
            community_attrs = G.nodes[highest_degree_node].copy()
            community_attrs.update(
                {"label_color": "#dd4444", "parent": None, "_id": community_node}
            )
            node_data = GraphNodeData(**community_attrs)
            G.add_node(community_node, **asdict(node_data))

            for node in community:
                G.nodes[node]["parent"] = community_node

        G.graph["num_communities"] = len(community_labels)

        # Gather edges between communities
        inter_edge_weight = defaultdict(int)
        inter_edge_pmids = defaultdict(list)
        to_remove = []
        for u, v, attrs in G.edges(data=True):
            if (c_0 := G.nodes[u]["parent"]) != (c_1 := G.nodes[v]["parent"]):
                if c_0 is None or c_1 is None:
                    logger.warning(f"[Error] Node {u} or {v} is not in any community")
                    continue
                to_remove.append((u, v))
                community_edge = tuple(sorted([c_0, c_1]))
                inter_edge_weight[community_edge] += attrs["scaled_edge_weight"]
                inter_edge_pmids[community_edge].extend(attrs["pmids"])

        G.remove_edges_from(to_remove)
        for (c_0, c_1), weight in inter_edge_weight.items():
            # Log-adjusted weight for balance
            try:
                weight = math.log(weight) * 5
                weight = 0.0 if weight < 0.0 else weight
            except ValueError:
                weight = 0.0
            pmids = list(set(inter_edge_pmids[(c_0, c_1)]))
            edge_data = CommunityEdgeData(
                _id=generate_uuid(),
                edge_weight=weight,
                scaled_edge_weight=weight,
                edge_width=int(max(weight, MIN_EDGE_WIDTH)),
                pmids=pmids,
            )
            G.add_edge(c_0, c_1, type="community", **asdict(edge_data))

    @staticmethod
    def log_graph_info(G: nx.Graph, parsed_pubtator: PubTatorResult):
        logger.info(f"# articles: {parsed_pubtator.num_pmids}")
        if num_communities := G.graph.get("num_communities", 0):
            logger.info(f"# communities: {num_communities}")
        logger.info(f"# nodes: {G.number_of_nodes() - num_communities}")
        logger.info(f"# edges: {G.number_of_edges()}")

    def save_network(self, G: nx.Graph):
        if self.savepath is None:
            return
        FORMAT_FUNCTION_MAP = {
            "xgmml": "netmedex.cytoscape_xgmml.save_as_xgmml",
            "html": "netmedex.cytoscape_js.save_as_html",
            "json": "netmedex.cytoscape_js.save_as_json",
        }

        module_path, func_name = FORMAT_FUNCTION_MAP[self.output_filetype].rsplit(".", 1)
        module = importlib.import_module(module_path)
        save_func = getattr(module, func_name)

        save_func(G, self.savepath)
        logger.info(f"Save graph to {self.savepath}")

    @staticmethod
    def load_graph(graph_pickle_path: str):
        with open(graph_pickle_path, "rb") as f:
            G = pickle.load(f)

        return G
