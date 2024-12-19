from pathlib import Path

import networkx as nx
from lxml import etree
from lxml.builder import E
from lxml.etree import QName

XML_NAMESPACE = {
    "cy": "http://www.cytoscape.org",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xlink": "http://www.w3.org/1999/xlink",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


for prefix, uri in XML_NAMESPACE.items():
    etree.register_namespace(prefix, uri)


TYPE_ATTR = {
    "string": {"type": "string", QName(XML_NAMESPACE["cy"], "type"): "String"},
    "boolean": {"type": "boolean", QName(XML_NAMESPACE["cy"], "type"): "Boolean"},
    "integer": {"type": "integer", QName(XML_NAMESPACE["cy"], "type"): "Integer"},
    "double": {"type": "double", QName(XML_NAMESPACE["cy"], "type"): "Double"},
}


def save_as_xgmml(G: nx.Graph, savepath):
    with open(savepath, "wb") as f:
        graph = create_graph_xml(G, Path(savepath).stem)
        f.write(
            etree.tostring(
                graph, encoding="utf-8", xml_declaration=True, standalone="yes", pretty_print=True
            )
        )


def create_graph_xml(G, graph_label="0"):
    _dummy_attr = {
        QName(XML_NAMESPACE["dc"], "dummy"): "",
        QName(XML_NAMESPACE["xlink"], "dummy"): "",
        QName(XML_NAMESPACE["rdf"], "dummy"): "",
    }
    _graph_attr = {
        "id": "0",
        "label": graph_label,
        "directed": "1",
        "xmlns": "http://www.cs.rpi.edu/XGMML",
        QName(XML_NAMESPACE["cy"], "documentVersion"): "3.0",
        **_dummy_attr,
    }

    graph = E.graph(_graph_attr, create_graphic_xml(), *create_node_xml(G), *create_edge_xml(G))

    # Delete attributes, keep namespace definition only
    for key in _dummy_attr:
        del graph.attrib[key]

    return graph


def create_graphic_xml():
    graph = E.graphics(
        # E.att(name_value("NETWORK_WIDTH", "795.0")),
        # E.att(name_value("NETWORK_DEPTH", "0.0")),
        # E.att(name_value("NETWORK_HEIGHT", "500.0")),
        # E.att(name_value("NETWORK_NODE_SELECTION", "true")),
        # E.att(name_value("NETWORK_EDGE_SELECTION", "true")),
        # E.att(name_value("NETWORK_BACKGROUND_PAINT", "#FFFFFF")),
        # E.att(name_value("NETWORK_CENTER_Z_LOCATION", "0.0")),
        # E.att(name_value("NETWORK_NODE_LABEL_SELECTION", "false")),
        # E.att(name_value("NETWORK_TITLE", "")),
    )

    return graph


def create_node_xml(G):
    node_collection = []
    for node in G.nodes(data=True):
        node_collection.append(_create_node_xml(node))

    return node_collection


def _create_node_xml(node):
    node_id, node_attr = node

    _node_attr = {"id": node_attr["_id"], "label": node_attr["name"]}
    _graphics_attr = {
        "width": "0.0",
        "h": "35.0",
        "w": "35.0",
        "z": "0.0",
        "x": str(round(node_attr["pos"][0], 3)),
        "y": str(round(node_attr["pos"][1], 3)),
        "type": node_attr["shape"],
        "outline": "#CCCCCC",
        "fill": node_attr["color"],
    }
    if node_attr["marked"]:
        _graphics_attr["outline"] = "#CF382C"
        _graphics_attr["width"] = "5.0"

    node = E.node(
        _node_attr,
        E.att(name_value("shared name", node_attr["name"])),
        E.att(name_value("name", node_attr["name"])),
        E.att(name_value("class", node_attr["type"])),
        E.graphics(
            _graphics_attr,
            # E.att(name_value("NODE_SELECTED", "false")),
            # E.att(name_value("NODE_NESTED_NETWORK_IMAGE_VISIBLE", "true")),
            # E.att(name_value("NODE_DEPTH", "0.0")),
            # E.att(name_value("NODE_SELECTED_PAINT", "#FFFF00")),
            # E.att(name_value("NODE_LABEL_ROTATION", "0.0")),
            # E.att(name_value("NODE_LABEL_WIDTH", "200.0")),
            # E.att(name_value("COMPOUND_NODE_PADDING", "10.0")),
            # E.att(name_value("NODE_LABEL_TRANSPARENCY", "255")),
            # E.att(name_value("NODE_LABEL_POSITION", "C,C,c,0.00,0.00")),
            # E.att(name_value("NODE_LABEL", node_attr["name"])),
            # E.att(name_value("NODE_VISIBLE", "true")),
            # E.att(name_value("NODE_LABEL_FONT_SIZE", "12")),
            # E.att(name_value("NODE_BORDER_STROKE", "SOLID")),
            # E.att(name_value("NODE_LABEL_FONT_FACE",
            #                  "SansSerif.plain,plain,12")),
            # E.att(name_value("NODE_BORDER_TRANSPARENCY", "255")),
            # E.att(name_value("COMPOUND_NODE_SHAPE", node_attr["shape"])),
            # E.att(name_value("NODE_LABEL_COLOR", "#000000")),
            # E.att(name_value("NODE_TRANSPARENCY", "255")),
        ),
    )

    return node


def name_value(name, value, with_type="string"):
    attr = {"name": name, "value": value}
    if with_type is not None:
        attr.update(TYPE_ATTR[with_type])
    return attr


def create_edge_xml(G):
    edge_collection = []
    for edge in G.edges(data=True):
        edge_collection.append(_create_edge_xml(edge, G))

    return edge_collection


def _create_edge_xml(edge, G):
    node_id_1, node_id_2, edge_attr = edge

    _edge_attr = {
        "id": edge_attr["_id"],
        "label": f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
        "source": G.nodes[node_id_1]["_id"],
        "target": G.nodes[node_id_2]["_id"],
        QName(XML_NAMESPACE["cy"], "directed"): "1",
    }

    _graphics_attr = {"width": str(edge_attr["scaled_edge_weight"]), "fill": "#848484"}

    edge = E.edge(
        _edge_attr,
        E.att(
            name_value(
                "shared name",
                f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
            )
        ),
        E.att(name_value("shared interaction", "interacts with")),
        E.att(
            name_value(
                "name",
                f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
            )
        ),
        E.att(name_value("selected", "0", with_type="boolean")),
        E.att(name_value("interaction", "interacts with")),
        E.att(name_value("edge weight", str(edge_attr["edge_weight"]), with_type="double")),
        E.att(
            name_value(
                "scaled edge weight", str(edge_attr["scaled_edge_weight"]), with_type="double"
            )
        ),
        E.att(name_value("edge width", str(edge_attr["edge_width"]), with_type="integer")),
        E.att(name_value("pubmed id", ",".join(edge_attr["pmids"]))),
        E.graphics(
            _graphics_attr,
            # E.att(name_value("EDGE_TOOLTIP", "")),
            # E.att(name_value("EDGE_SELECTED", "false")),
            # E.att(name_value("EDGE_TARGET_ARROW_SIZE", "6.0")),
            # E.att(name_value("EDGE_LABEL", "")),
            # E.att(name_value("EDGE_LABEL_TRANSPARENCY", "255")),
            # E.att(name_value("EDGE_STACKING_DENSITY", "0.5")),
            # E.att(name_value("EDGE_TARGET_ARROW_SHAPE", "NONE")),
            # E.att(
            #     name_value("EDGE_SOURCE_ARROW_UNSELECTED_PAINT",
            #                "#000000")),
            # E.att(name_value("EDGE_TARGET_ARROW_SELECTED_PAINT",
            #                  "#FFFF00")),
            # E.att(
            #     name_value(
            #         "EDGE_TARGET_ARROW_UNSELECTED_PAINT",
            #         "#000000")),
            # E.att(name_value("EDGE_SOURCE_ARROW_SHAPE", "None")),
            # E.att(name_value("EDGE_BEND", "")),
            # E.att(name_value("EDGE_STACKING", "AUTO_BEND")),
            # E.att(name_value("EDGE_LABEL_COLOR", "#000000")),
            # E.att(name_value("EDGE_TRANSPARENCY", "255")),
            # E.att(name_value("EDGE_LABEL_ROTATION", "0.0")),
            # E.att(name_value("EDGE_LABEL_WIDTH", "200.0")),
            # E.att(name_value("EDGE_CURVED", "true")),
            # E.att(name_value("EDGE_SOURCE_ARROW_SIZE", "6.0")),
            # E.att(name_value("EDGE_VISIBLE", "true")),
            # E.att(name_value("EDGE_LINE_TYPE", "SOLID")),
            # E.att(name_value("EDGE_STROKE_SELECTED_PAINT", "#FF0000")),
            # E.att(name_value("EDGE_LABEL_FONT_SIZE", "10")),
            # E.att(
            #     name_value("EDGE_LABEL_FONT_FACE",
            #                "Dialog.plain,plain,10")),
            # E.att(name_value("EDGE_Z_ORDER", "0.0")),
            # E.att(name_value("EDGE_SOURCE_ARROW_SELECTED_PAINT",
            #                  "#FFFF00")),
        ),
    )

    return edge
