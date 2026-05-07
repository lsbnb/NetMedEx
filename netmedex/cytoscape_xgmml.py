import json
import xml.etree.ElementTree as ET

import networkx as nx

def save_as_xgmml(G: nx.Graph, savepath):
    simplified = _build_simple_graph(G)
    _write_xgmml(simplified, savepath)


def _write_xgmml(G: nx.Graph, path):
    """Custom XGMML writer for NetworkX graphs."""
    root = ET.Element("graph", {
        "directed": "1" if G.is_directed() else "0",
        "id": "0",
        "label": "NetMedEx Network",
        "xmlns": "http://www.cs.rpi.edu/XGMML"
    })

    # Add network attributes
    for key, val in G.graph.items():
        if key == "name":
            continue
        xgmml_type = _get_xgmml_type(val)
        ET.SubElement(root, "att", {
            "name": str(key),
            "value": _to_xgmml_value(val),
            "type": xgmml_type
        })

    # Add nodes
    for node_id, data in G.nodes(data=True):
        node_elem = ET.SubElement(root, "node", {
            "id": str(node_id),
            "label": str(data.get("label", node_id))
        })

        # Add visual information
        fill = data.get("color", "#888888")
        shape = data.get("shape", "ELLIPSE")
        ET.SubElement(node_elem, "graphics", {
            "type": str(shape),
            "h": "40.0",
            "w": "40.0",
            "fill": str(fill),
            "outline": "#666666",
            "width": "1.0"
        })

        for key, val in data.items():
            if key in ("label", "color", "shape", "label_color", "shared name", "name"):
                if key in ("shared name", "name"):
                    # Ensure standard names are written as attributes too
                    xgmml_type = _get_xgmml_type(val)
                    ET.SubElement(node_elem, "att", {
                        "name": str(key),
                        "value": _to_xgmml_value(val),
                        "type": xgmml_type
                    })
                continue
            
            xgmml_type = _get_xgmml_type(val)
            ET.SubElement(node_elem, "att", {
                "name": str(key),
                "value": _to_xgmml_value(val),
                "type": xgmml_type
            })

    # Add edges
    edge_counter = 1
    for u, v, data in G.edges(data=True):
        edge_id = str(data.get("id", f"e{edge_counter}"))
        edge_counter += 1
        edge_elem = ET.SubElement(root, "edge", {
            "id": edge_id,
            "source": str(u),
            "target": str(v),
            "label": str(data.get("label", f"{u} -> {v}"))
        })

        # Add visual information
        width = data.get("edge_width", 1.0)
        ET.SubElement(edge_elem, "graphics", {
            "width": str(width),
            "fill": "#888888"
        })

        for key, val in data.items():
            if key in ("label", "edge_width", "edge_weight", "shared name", "name", "interaction"):
                if key in ("shared name", "name", "interaction"):
                    # Cytoscape needs these as explicit atts as well
                    xgmml_type = _get_xgmml_type(val)
                    ET.SubElement(edge_elem, "att", {
                        "name": str(key),
                        "value": _to_xgmml_value(val),
                        "type": xgmml_type
                    })
                continue
            
            xgmml_type = _get_xgmml_type(val)
            ET.SubElement(edge_elem, "att", {
                "name": str(key),
                "value": _to_xgmml_value(val),
                "type": xgmml_type
            })

    tree = ET.ElementTree(root)
    with open(path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)


def _build_simple_graph(G: nx.Graph) -> nx.Graph:
    simplified = nx.DiGraph()
    simplified.graph.update(G.graph)

    for node, data in G.nodes(data=True):
        node_id = data.get("_id", node)
        attributes = {
            key: value
            for key, value in data.items()
            if key not in ("_id", "pos")
        }
        node_name = data.get("name", data.get("label", str(node_id)))
        attributes.setdefault("label", node_name)
        attributes.setdefault("shared name", node_name)
        attributes.setdefault("name", node_name)
        simplified.add_node(node_id, **attributes)

    for u, v, data in G.edges(data=True):
        source_id = G.nodes[u].get("_id", u)
        target_id = G.nodes[v].get("_id", v)
        source_name = G.nodes[u].get("name", G.nodes[u].get("label", str(source_id)))
        target_name = G.nodes[v].get("name", G.nodes[v].get("label", str(target_id)))

        attributes = {
            key: value
            for key, value in data.items()
            if key not in ("_id", "relations")
        }
        # Add a flat list of PMIDs for easy reading in Cytoscape
        relations = data.get("relations", {})
        attributes["pmid_list"] = sorted(set(relations.keys()))
        attributes["relations"] = _serialize_relations(relations)
        
        # Use primary_relation if available, else fallback
        interaction_type = attributes.get("primary_relation", "interacts with")
        edge_name = f"{source_name} ({interaction_type}) {target_name}"
        
        attributes["label"] = edge_name
        attributes["shared name"] = edge_name
        attributes["name"] = edge_name
        attributes["interaction"] = interaction_type
        
        simplified.add_edge(source_id, target_id, **attributes)

    return simplified


def _get_xgmml_type(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    return "string"


def _to_xgmml_value(value) -> str:
    if isinstance(value, (list, set, tuple, dict)):
        return json.dumps(_to_jsonable(value), ensure_ascii=False)
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _to_jsonable(value):
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return value


def _serialize_relations(relations):
    if not relations:
        return ""

    normalized = {
        str(pmid): sorted(set(rel_list))
        for pmid, rel_list in relations.items()
        if pmid and rel_list
    }
    return json.dumps(normalized, ensure_ascii=False)
