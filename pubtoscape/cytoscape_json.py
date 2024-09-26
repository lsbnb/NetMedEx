import networkx as nx
import json


def save_as_json(G: nx.Graph, savepath: str):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_json(G)
        f.write(json.dumps(cytoscape_js))


def create_cytoscape_json(G: nx.Graph):
    elements = {"elements": {"nodes": [], "edges": []}}
    for node in G.nodes(data=True):
        elements["elements"]["nodes"].append(create_cytoscape_node(node))

    for edge in G.edges(data=True):
        elements["elements"]["edges"].append(create_cytoscape_edge(edge, G))

    return elements


def create_cytoscape_node(node):
    node_id, node_attr = node

    node_info = {
        "data": {
            "id": node_attr["_id"],
            "parent": node_attr.get("parent", None),
            "color": node_attr["color"],
            "label": node_attr["name"],
            "label_color": node_attr["label_color"],
            "shape": node_attr["shape"].lower(),
        },
        "position": {
            "x": round(node_attr["pos"][0], 3),
            "y": round(node_attr["pos"][1], 3),
        }
    }

    # Community nodes
    if node_attr["_id"].startswith("c"):
        node_info["classes"] = "top-center"

    return node_info


def create_cytoscape_edge(edge, G):
    node_id_1, node_id_2, edge_attr = edge

    edge_info = {
        "data": {
            # Add this will sometimes cause dash_cytoscape to throw node source or target not found
            # "id": edge_attr["_id"],
            "source": G.nodes[node_id_1]["_id"],
            "target": G.nodes[node_id_2]["_id"],
            "label": f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
            "weight": round(float(edge_attr["scaled_edge_weight"]), 1),
        }
    }

    return edge_info
