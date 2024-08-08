import csv
import importlib
import logging
import re
import sys
from argparse import ArgumentParser
from collections import defaultdict
from itertools import count
from pathlib import Path
from typing import DefaultDict, Literal

import networkx as nx

from pubtoscape.stemmers import s_stemmer
from pubtoscape.utils import config_logger

# VARIANT_PATTERN = re.compile(r"CorrespondingGene:.*CorrespondingSpecies:\d+")
MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)")
}

COLOR_MAP = {
    "Chemical": "#67A9CF",
    "Gene": "#74C476",
    "Species": "#FD8D3C",
    "Disease": "#8C96C6",
    "DNAMutation": "#FCCDE5",
    "ProteinMutation": "#FA9FB5",
    "CellLine": "#BDBDBD",
    "SNP": "#FFFFB3"
}
SHAPE_MAP = {
    "Chemical": "ELLIPSE",
    "Gene": "TRIANGLE",
    "Species": "DIAMOND",
    "Disease": "ROUNDRECTANGLE",
    "DNAMutation": "PARALLELOGRAM",
    "ProteinMutation": "HEXAGON",
    "CellLine": "VEE",
    "SNP": "OCTAGON"
}

mesh_info = {}
logger = logging.getLogger(__name__)


def pubtator2cytoscape(filepath, savepath, args):
    G = nx.Graph()
    result = parse_pubtator(filepath, args.index_by)
    add_node_to_graph(G, result["node_dict"], result["non_isolated_nodes"])
    add_edge_to_graph(G, result["edge_dict"], args.pmid_weight)
    remove_edges_by_weight(G, args.cut_weight)
    remove_isolated_nodes(G)

    pos = nx.spring_layout(G,
                           weight="scaled_weight",
                           scale=300,
                           k=0.25,
                           iterations=15)
    nx.set_node_attributes(G, pos, "pos")

    save_network(G, savepath, args.format)


def save_network(G: nx.Graph,
                 savepath: str,
                 format: Literal["xgmml", "html"] = "xgmml"):
    FORMAT_FUNCTION_MAP = {
        "xgmml": "pubtoscape.cytoscape_xgmml.save_as_xgmml",
        "html": "pubtoscape.cytoscape_html.save_as_html",
    }

    module_path, func_name = FORMAT_FUNCTION_MAP[format].rsplit(".", 1)
    module = importlib.import_module(module_path)
    save_func = getattr(module, func_name)

    save_func(G, savepath)

    logger.info(f"# nodes: {G.number_of_nodes()}")
    logger.info(f"# edges: {G.number_of_edges()}")
    logger.info(f"Save graph to {savepath}")


def parse_pubtator(filepath, index_by):
    node_dict = {}
    edge_dict = defaultdict(list)
    non_isolated_nodes = set()
    pmid = -1
    last_pmid = -1
    node_dict_each = {}
    with open(filepath) as f:
        for line in f.readlines():
            if _is_title(line):
                pmid = _find_pmid(line)
                continue
            if index_by == "relation":
                parse_line_relation(line, node_dict, edge_dict, non_isolated_nodes)
            else:
                if pmid != last_pmid:
                    create_complete_graph(node_dict_each, edge_dict, last_pmid)
                    last_pmid = pmid
                    node_dict_each = {}
                if get_line_type(line) == "annotation":
                    if index_by == "name":
                        add_node_by_name(line, node_dict, node_dict_each)
                    elif index_by == "mesh":
                        add_node_by_mesh(line, node_dict, node_dict_each)
        create_complete_graph(node_dict_each, edge_dict, pmid)
    if index_by in ("name", "mesh"):
        non_isolated_nodes = set(node_dict.keys())

    return {
        "node_dict": node_dict,
        "non_isolated_nodes": non_isolated_nodes,
        "edge_dict": edge_dict
    }


def _is_title(line):
    return line.find("|t|") != -1


def _find_pmid(line):
    return line.split("|t|")[0]


def parse_line_relation(line, node_dict: dict,
                        edge_dict: DefaultDict[tuple, list],
                        non_isolated_nodes: set):
    line_type = get_line_type(line)
    if line_type == "annotation":
        add_node_by_mesh(line, node_dict, {})
    elif line_type == "relation":
        create_edges_for_relations(line, edge_dict, non_isolated_nodes)


def create_edges_for_relations(line, edge_dict, non_isolated_nodes):
    pmid, relationship, name_1, name_2 = line.strip("\n").split("\t")
    # TODO: better way to deal with DNAMutation notation inconsistency
    name_1 = name_1.split("|")[0]
    name_2 = name_2.split("|")[0]
    edge_dict[(name_1, name_2)].append({
            "pmid": pmid,
            "relationship": relationship,
            "_id": id_counter()
        })
    non_isolated_nodes.add(name_1)
    non_isolated_nodes.add(name_2)


def add_node_by_mesh(line, node_dict, node_dict_each):
    pmid, start, end, name, type, mesh = line.strip("\n").split("\t")

    # Skip line with no id
    if mesh in ("", "-"):
        return

    if type in ("DNAMutation", "ProteinMutation", "SNP"):
        res = {}
        for key, pattern in MUTATION_PATTERNS.items():
            try:
                res[key] = f"{re.search(pattern, mesh).group(1)};"
            except AttributeError:
                res[key] = ""

        if type == "DNAMutation":
            mesh = (
                f'{res["gene"]}{res["species"]}{res["variantgroup"]}'
                f'{res["tmvar"].split("|")[0]}'
            ).strip(";")
        elif type == "ProteinMutation":
            mesh = f'{res["rs"]}{res["hgvs"]}{res["gene"]}'.strip(";")
        elif type == "SNP":
            mesh = f'{res["rs"]}{res["hgvs"]}{res["gene"]}'.strip(";")
        mesh_list = [mesh]
    elif type == "Gene":
        mesh_list = mesh.split(";")
    else:
        mesh_list = [mesh]

    for each_mesh in mesh_list:
        if not _node_id_collision(node_dict, name, type, each_mesh):
            node_dict.setdefault(
                each_mesh, {
                    "mesh": mesh,
                    "type": type,
                    "name": name,
                    "_id": id_counter()
                })

        node_dict_each[each_mesh] = node_dict[each_mesh]


def _node_id_collision(node_dict, name, type, id):
    is_collision = False
    if id in node_dict and type != node_dict[id]["type"]:
        current_line = {
            "id": id,
            "type": type,
            "name": name,
        }
        logger.debug(f"Found collision of MeSH:\n{node_dict[id]}\n{current_line}")
        logger.debug("Discard the latter\n")
        is_collision = True

    return is_collision


def create_complete_graph(node_dict_each, edge_dict, pmid):
    for i, name_1 in enumerate(node_dict_each.keys()):
        for j, name_2 in enumerate(node_dict_each.keys()):
            if i >= j:
                continue
            if edge_dict.get((name_2, name_1), []):
                edge_dict[(name_2, name_1)].append({
                    "pmid": pmid,
                    "_id": id_counter()
                })
            else:
                edge_dict[(name_1, name_2)].append({
                    "pmid": pmid,
                    "_id": id_counter()
                })


def add_node_by_name(line, node_dict, node_dict_each):
    global mesh_info
    pmid, start, end, name, type, mesh = line.strip("\n").split("\t")

    # Convert non-mesh terms to lowercase
    if mesh in ("-", ""):
        name = name.lower()

    # Remove plural
    name = s_stemmer(name)

    node_info = {
        "mesh": mesh,
        "type": type,
        "name": name,
        "_id": id_counter()
    }

    if name in node_dict and type != node_dict[name]["type"]:
        logger.debug(f"Found collision of name:\n{node_dict[name]}\n{node_info}")
        logger.debug("Discard the latter\n")

    # Non-standardized terms
    if mesh in ("-", ""):
        node_dict.setdefault(name, node_info)
        node_dict_each[name] = node_dict[name]
    # Keep unique MeSH terms
    elif mesh not in mesh_info:
        mesh_info[mesh] = node_info
        node_dict.setdefault(name, node_info)
        node_dict_each[name] = node_dict[name]
    else:
        node_dict_each[mesh_info[mesh]["name"]] = mesh_info[mesh]


def get_line_type(line):
    line_split_len = len(line.split("\t"))
    if line_split_len == 4:
        line_type = "relation"
    elif line_split_len == 6:
        line_type = "annotation"
    else:
        line_type = "unknown"

    return line_type


def id_counter(id=count(1)):
    return str(next(id))


def add_node_to_graph(G: nx.Graph, node_dict, non_isolated_nodes):
    # TODO: add feature: mark specific names
    marked = False
    for id in non_isolated_nodes:
        try:
            G.add_node(id,
                       color=COLOR_MAP[node_dict[id]["type"]],
                       shape=SHAPE_MAP[node_dict[id]["type"]],
                       type=node_dict[id]["type"],
                       name=node_dict[id]["name"],
                       _id=node_dict[id]["_id"],
                       marked=marked)
        except KeyError:
            logger.debug(f"Skip node: {id}")


def add_edge_to_graph(G: nx.Graph, edge_counter, weight_csv):
    weights = {}
    if weight_csv is not None:
        with open(weight_csv, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                weights[row[0]] = float(row[1])

    for pair, records in edge_counter.items():
        pmids = [str(record["pmid"]) for record in records]
        unique_pmids = set(pmids)
        edge_weight = round(sum([weights.get(pmid, 1) for pmid in unique_pmids]), 2)
        try:
            G.add_edge(pair[0],
                       pair[1],
                       _id=records[0]["_id"],
                       weight=edge_weight,
                       pmids=",".join(list(unique_pmids)))
        except Exception:
            logger.debug(f"Skip edge: ({pair[0]}, {pair[1]})")

    # Scaled weight (scaled by max only)
    weights = nx.get_edge_attributes(G, "weight")
    min_width = 1
    max_width = 20
    max_weight = max(weights.values())
    scale_factor = min(max_width / max_weight, 1)
    for edge, weight in weights.items():
        G.edges[edge]["scaled_weight"] = max(int(round(weight * scale_factor, 0)),
                                             min_width)


def remove_edges_by_weight(G: nx.Graph, cut_weight):
    scaled_weights = nx.get_edge_attributes(G, "scaled_weight")
    for edge, scaled_weight in scaled_weights.items():
        if scaled_weight < cut_weight:
            G.remove_edge(edge[0], edge[1])


def remove_isolated_nodes(G: nx.Graph):
    G.remove_nodes_from(list(nx.isolates(G)))


def main():
    args = parse_args(sys.argv[1:])

    config_logger(args.debug)

    input_filepath = Path(args.input)
    if args.output is None:
        output_filepath = input_filepath.with_suffix(".xgmml")
    else:
        output_filepath = Path(args.output)
        output_filepath.parent.mkdir(parents=True, exist_ok=True)

    pubtator2cytoscape(input_filepath, output_filepath, args)


def parse_args(args):
    parser = setup_argparsers()
    return parser.parse_args(args)


def setup_argparsers():
    parser = ArgumentParser()
    parser.add_argument("-i",
                        "--input",
                        type=str,
                        help="Path to the pubtator file")
    parser.add_argument("-o",
                        "--output",
                        default=None,
                        help="Output path (default: [INPUT FILEPATH].xgmml)")
    parser.add_argument(
        "-w",
        "--cut_weight",
        type=int,
        default=5,
        help="Discard the edges with weight smaller than the specified value (default: 5)"
    )
    parser.add_argument("-f",
                        "--format",
                        choices=["xgmml", "html"],
                        default="html",
                        help="Output format (default: html)")
    parser.add_argument("--index_by",
                        choices=["mesh", "name", "relation"],
                        default="name",
                        help="Extract nodes and edges by (default: name)")
    parser.add_argument("--pmid_weight",
                        default=None,
                        help="csv file for the weight of the edge from a PMID (default: 1)")
    parser.add_argument("--debug",
                        action="store_true",
                        help="Print debug information")

    return parser


if __name__ == "__main__":
    main()
