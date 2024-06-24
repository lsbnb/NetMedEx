import re
from argparse import ArgumentParser
from collections import defaultdict
from itertools import count
from typing import DefaultDict
from pathlib import Path
import networkx as nx
from lxml import etree
from lxml.builder import E
import csv
from lxml.etree import QName

XML_NAMESPACE = {
    "cy": "http://www.cytoscape.org",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xlink": "http://www.w3.org/1999/xlink",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
}
for prefix, uri in XML_NAMESPACE.items():
    etree.register_namespace(prefix, uri)

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
# PARSE_LINE_TYPE = ["annotation", "relation"][1]
TYPE_ATTR = {
    "string": {
        "type": "string",
        QName(XML_NAMESPACE["cy"], "type"): "String"
    },
    "boolean": {
        "type": "boolean",
        QName(XML_NAMESPACE["cy"], "type"): "Boolean"
    },
    "integer": {
        "type": "integer",
        QName(XML_NAMESPACE["cy"], "type"): "Integer"
    },
    "double": {
        "type": "double",
        QName(XML_NAMESPACE["cy"], "type"): "Double"
    },
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
    "Disease": "ROUND_RECTANGLE",
    "DNAMutation": "PARALLELOGRAM",
    "ProteinMutation": "HEXAGON",
    "CellLine": "VEE",
    "SNP": "OCTAGON"
}

mesh_info = {}


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

    save_xgmml(G, savepath)


def save_xgmml(G: nx.Graph, savepath):
    with open(savepath, "wb") as f:
        graph = create_graph_xml(G, Path(savepath).stem)
        f.write(
            etree.tostring(graph,
                           encoding="utf-8",
                           xml_declaration=True,
                           standalone="yes",
                           pretty_print=True))

    print(f"# nodes: {G.number_of_nodes()}")
    print(f"# edges: {G.number_of_edges()}")
    print(f"Save graph to {savepath}")


def parse_pubtator(filepath, index_by):
    node_dict = {}
    edge_dict = defaultdict(list)
    non_isolated_nodes = set()
    pmid = -1
    last_pmid = -1
    node_dict_each = {}
    with open(filepath) as f:
        for line in f.readlines():
            if is_title(line):
                pmid = find_pmid(line)
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


def is_title(line):
    return line.find("|t|") != -1


def find_pmid(line):
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
            "xml_id": xml_id_counter()
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
        if not node_id_collision(node_dict, name, type, each_mesh):
            node_dict.setdefault(
                each_mesh, {
                    "mesh": mesh,
                    "type": type,
                    "name": name,
                    "xml_id": xml_id_counter()
                })

        node_dict_each[each_mesh] = node_dict[each_mesh]


def node_id_collision(node_dict, name, type, id):
    is_collision = False
    if id in node_dict and type != node_dict[id]["type"]:
        current_line = {
            "id": id,
            "type": type,
            "name": name,
        }
        print(f"Found collision of MeSH:\n{node_dict[id]}\n{current_line}")
        print("Discard the latter\n")
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
                    "xml_id": xml_id_counter()
                })
            else:
                edge_dict[(name_1, name_2)].append({
                    "pmid": pmid,
                    "xml_id": xml_id_counter()
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
        "xml_id": xml_id_counter()
    }

    if name in node_dict and type != node_dict[name]["type"]:
        print(f"Found collision of name:\n{node_dict[name]}\n{node_info}")
        print("Discard the latter\n")

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


def xml_id_counter(id=count(1)):
    return str(next(id))


def name_value(name, value, with_type="string"):
    attr = {"name": name, "value": value}
    if with_type is not None:
        attr.update(TYPE_ATTR[with_type])
    return attr


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
                       xml_id=node_dict[id]["xml_id"],
                       marked=marked)
        except KeyError:
            print(f"Skip node: {id}")


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
                       xml_id=records[0]["xml_id"],
                       weight=edge_weight,
                       pmids=",".join(list(unique_pmids)))
        except Exception:
            print(f"Skip edge: ({pair[0]}, {pair[1]})")

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


def create_graph_xml(G, graph_label="0"):
    _dummy_attr = {
        QName(XML_NAMESPACE["dc"], "dummy"): "",
        QName(XML_NAMESPACE["xlink"], "dummy"): "",
        QName(XML_NAMESPACE["rdf"], "dummy"): ""
    }
    _graph_attr = {
        "id": "0",
        "label": graph_label,
        "directed": "1",
        "xmlns": "http://www.cs.rpi.edu/XGMML",
        QName(XML_NAMESPACE["cy"], "documentVersion"): "3.0",
        **_dummy_attr
    }

    graph = E.graph(_graph_attr, create_graphic_xml(), *create_node_xml(G),
                    *create_edge_xml(G))

    # Delete attributes, keep namespace definition only
    for key in _dummy_attr:
        del graph.attrib[key]

    return graph


def create_graphic_xml():
    graph = (E.graphics(
        E.att(name_value("NETWORK_WIDTH", "795.0")),
        E.att(name_value("NETWORK_DEPTH", "0.0")),
        E.att(name_value("NETWORK_HEIGHT", "500.0")),
        E.att(name_value("NETWORK_NODE_SELECTION", "true")),
        E.att(name_value("NETWORK_EDGE_SELECTION", "true")),
        E.att(name_value("NETWORK_BACKGROUND_PAINT", "#FFFFFF")),
        E.att(name_value("NETWORK_CENTER_Z_LOCATION", "0.0")),
        E.att(name_value("NETWORK_NODE_LABEL_SELECTION", "false")),
        E.att(name_value("NETWORK_TITLE", "")),
    ))

    return graph


def create_node_xml(G):
    node_collection = []
    for node in G.nodes(data=True):
        node_collection.append(_create_node_xml(node))

    return node_collection


def _create_node_xml(node):
    node_id, node_attr = node

    _node_attr = {"id": node_attr["xml_id"], "label": node_attr["name"]}
    _graphics_attr = {
        "width": "0.0",
        "h": "35.0",
        "w": "35.0",
        "z": "0.0",
        "x": str(round(node_attr["pos"][0], 3)),
        "y": str(round(node_attr["pos"][1], 3)),
        "type": node_attr["shape"],
        "outline": "#CCCCCC",
        "fill": node_attr["color"]
    }
    if node_attr["marked"]:
        _graphics_attr["outline"] = "#CF382C"
        _graphics_attr["width"] = "5.0"

    node = (E.node(
        _node_attr, E.att(name_value("shared name", node_attr["name"])),
        E.att(name_value("name", node_attr["name"])),
        E.att(name_value("class", node_attr["type"])),
        E.graphics(
            _graphics_attr,
            E.att(name_value("NODE_SELECTED", "false")),
            E.att(name_value("NODE_NESTED_NETWORK_IMAGE_VISIBLE", "true")),
            E.att(name_value("NODE_DEPTH", "0.0")),
            E.att(name_value("NODE_SELECTED_PAINT", "#FFFF00")),
            E.att(name_value("NODE_LABEL_ROTATION", "0.0")),
            E.att(name_value("NODE_LABEL_WIDTH", "200.0")),
            E.att(name_value("COMPOUND_NODE_PADDING", "10.0")),
            E.att(name_value("NODE_LABEL_TRANSPARENCY", "255")),
            E.att(name_value("NODE_LABEL_POSITION", "C,C,c,0.00,0.00")),
            E.att(name_value("NODE_LABEL", node_attr["name"])),
            E.att(name_value("NODE_VISIBLE", "true")),
            E.att(name_value("NODE_LABEL_FONT_SIZE", "12")),
            E.att(name_value("NODE_BORDER_STROKE", "SOLID")),
            E.att(name_value("NODE_LABEL_FONT_FACE",
                             "SansSerif.plain,plain,12")),
            E.att(name_value("NODE_BORDER_TRANSPARENCY", "255")),
            E.att(name_value("COMPOUND_NODE_SHAPE", node_attr["shape"])),
            E.att(name_value("NODE_LABEL_COLOR", "#000000")),
            E.att(name_value("NODE_TRANSPARENCY", "255")),
        )))

    return node


def create_edge_xml(G):
    edge_collection = []
    for edge in G.edges(data=True):
        edge_collection.append(_create_edge_xml(edge, G))

    return edge_collection


def _create_edge_xml(edge, G):
    node_id_1, node_id_2, edge_attr = edge

    _edge_attr = {
        "id": edge_attr["xml_id"],
        "label":
        f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
        "source": G.nodes[node_id_1]["xml_id"],
        "target": G.nodes[node_id_2]["xml_id"],
        QName(XML_NAMESPACE["cy"], "directed"): "1"
    }

    _graphics_attr = {
        "width": str(edge_attr["scaled_weight"]),
        "fill": "#848484"
    }

    edge = (
        E.edge(
            _edge_attr,
            E.att(
                name_value(
                    "shared name",
                    f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}"
                )),
            E.att(name_value("shared interaction", "interacts with")),
            E.att(
                name_value(
                    "name",
                    f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}"
                )),
            E.att(name_value("selected", "0", with_type="boolean")),
            E.att(name_value("interaction", "interacts with")),
            E.att(
                name_value("weight",
                           str(edge_attr["weight"]),
                           with_type="double")),
            # TODO: implement scaled weight
            E.att(
                name_value("scaled weight",
                           str(edge_attr["scaled_weight"]),
                           with_type="integer")),
            E.att(name_value("pubmed id", edge_attr["pmids"])),
            E.graphics(
                _graphics_attr,
                E.att(name_value("EDGE_TOOLTIP", "")),
                E.att(name_value("EDGE_SELECTED", "false")),
                E.att(name_value("EDGE_TARGET_ARROW_SIZE", "6.0")),
                E.att(name_value("EDGE_LABEL", "")),
                E.att(name_value("EDGE_LABEL_TRANSPARENCY", "255")),
                E.att(name_value("EDGE_STACKING_DENSITY", "0.5")),
                E.att(name_value("EDGE_TARGET_ARROW_SHAPE", "NONE")),
                E.att(
                    name_value("EDGE_SOURCE_ARROW_UNSELECTED_PAINT",
                               "#000000")),
                E.att(name_value("EDGE_TARGET_ARROW_SELECTED_PAINT",
                                 "#FFFF00")),
                E.att(
                    name_value(
                        "EDGE_TARGET_ARROW_UNSELECTED_PAINT",
                        "#000000")),
                E.att(name_value("EDGE_SOURCE_ARROW_SHAPE", "None")),
                E.att(name_value("EDGE_BEND", "")),
                E.att(name_value("EDGE_STACKING", "AUTO_BEND")),
                E.att(name_value("EDGE_LABEL_COLOR", "#000000")),
                E.att(name_value("EDGE_TRANSPARENCY", "255")),
                E.att(name_value("EDGE_LABEL_ROTATION", "0.0")),
                E.att(name_value("EDGE_LABEL_WIDTH", "200.0")),
                E.att(name_value("EDGE_CURVED", "true")),
                E.att(name_value("EDGE_SOURCE_ARROW_SIZE", "6.0")),
                E.att(name_value("EDGE_VISIBLE", "true")),
                E.att(name_value("EDGE_LINE_TYPE", "SOLID")),
                E.att(name_value("EDGE_STROKE_SELECTED_PAINT", "#FF0000")),
                E.att(name_value("EDGE_LABEL_FONT_SIZE", "10")),
                E.att(
                    name_value("EDGE_LABEL_FONT_FACE",
                               "Dialog.plain,plain,10")),
                E.att(name_value("EDGE_Z_ORDER", "0.0")),
                E.att(name_value("EDGE_SOURCE_ARROW_SELECTED_PAINT",
                                 "#FFFF00")),
            )))

    return edge


def s_stemmer(word: str):
    if word.endswith("ies") and not word.endswith(("eies", "aies")):
        word = word[:-3] + "y"
    elif word.endswith("es") and not word.endswith(("aes", "ees", "oes")):
        word = word[:-1]
    elif word.endswith("s") and not word.endswith(("is", "us", "ss")):
        word = word[:-1]

    return word


if __name__ == "__main__":
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
    parser.add_argument("--index_by",
                        choices=["mesh", "name", "relation"],
                        default="name",
                        help="Extract nodes and edges by")
    parser.add_argument("--pmid_weight",
                        default=None,
                        help="csv file for the weight of the edge from a PMID (default: 1)")
    args = parser.parse_args()

    input_filepath = Path(args.input)
    if args.output is None:
        output_filepath = input_filepath.with_suffix(".xgmml")
    else:
        output_filepath = Path(args.output)
        output_filepath.parent.mkdir(parents=True, exist_ok=True)

    pubtator2cytoscape(input_filepath, output_filepath, args)
