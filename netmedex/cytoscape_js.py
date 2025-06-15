import json
import re
from typing import Literal

import networkx as nx

from netmedex.cytoscape_html_template import HTML_TEMPLATE

SHAPE_JS_MAP = {"PARALLELOGRAM": "RHOMBOID"}
COMMUNITY_NODE_PATTERN = re.compile(r"^c\d+$")


def save_as_html(G: nx.Graph, savepath: str, layout="preset"):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G, style="cyjs")
        f.write(HTML_TEMPLATE.format(cytoscape_js=json.dumps(cytoscape_js), layout=layout))


def save_as_json(G: nx.Graph, savepath: str):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G, style="dash")
        f.write(json.dumps(cytoscape_js))


def create_cytoscape_js(G: nx.Graph, style: Literal["dash", "cyjs"] = "cyjs"):
    # TODO: Check whether to set id for edges
    with_id = False
    nodes = [create_cytoscape_node(node) for node in G.nodes(data=True)]
    edges = [create_cytoscape_edge(edge, G, with_id) for edge in G.edges(data=True)]

    if style == "cyjs":
        elements = nodes + edges
    elif style == "dash":
        elements = {"elements": {"nodes": nodes, "edges": edges}}

    return elements


def create_cytoscape_node(node):
    def convert_shape(shape):
        return SHAPE_JS_MAP.get(shape, shape).lower()

    node_id, node_attr = node

    node_info = {
        "data": {
            "id": node_attr["_id"],
            "parent": node_attr.get("parent", None),
            "color": node_attr["color"],
            "label_color": node_attr["label_color"],
            "label": node_attr["name"],
            "shape": convert_shape(node_attr["shape"]),
            "pmids": list(node_attr["pmids"]),
            "num_articles": node_attr["num_articles"],
            "standardized_id": node_attr["mesh"],
            "node_type": node_attr["type"],
        },
        "position": {
            "x": round(node_attr["pos"][0], 3),
            "y": round(node_attr["pos"][1], 3),
        },
    }

    # Community nodes
    if COMMUNITY_NODE_PATTERN.search(node_attr["_id"]):
        node_info["classes"] = "top-center"

    return node_info


def create_cytoscape_edge(edge, G, with_id=True):
    node_id_1, node_id_2, edge_attr = edge
    if edge_attr["type"] == "community":
        pmids = list(edge_attr["pmids"])
    else:
        pmids = list(edge_attr["relations"].keys())

    edge_info = {
        "data": {
            "source": G.nodes[node_id_1]["_id"],
            "target": G.nodes[node_id_2]["_id"],
            "label": f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
            "weight": round(max(float(edge_attr["edge_width"]), 1), 1),
            "pmids": pmids,
            "edge_type": edge_attr["type"],
        }
    }

    if with_id:
        edge_info["data"]["id"] = edge_attr["_id"]

    return edge_info
