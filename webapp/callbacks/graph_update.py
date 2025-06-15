import uuid

import dash_cytoscape as cyto
from dash import ClientsideFunction, Input, Output, State, clientside_callback, no_update

from netmedex.cytoscape_js import create_cytoscape_js
from webapp.callbacks.graph_utils import rebuild_graph


def generate_cytoscape_js_network(graph_layout, graph_json):
    if graph_json is not None:
        elements = [*graph_json["elements"]["nodes"], *graph_json["elements"]["edges"]]
    else:
        elements = []

    cytoscape_graph = cyto.Cytoscape(
        id="cy",
        minZoom=0.1,
        maxZoom=20,
        wheelSensitivity=0.3,
        style={},
        layout={"name": graph_layout},
        stylesheet=[
            {
                "selector": "node",
                "style": {
                    "text-valign": "center",
                    "label": "data(label)",
                    "shape": "data(shape)",
                    "color": "data(label_color)",
                    "background-color": "data(color)",
                },
            },
            {
                "selector": ":parent",
                "style": {
                    "background-opacity": 0.3,
                },
            },
            {
                "selector": "edge",
                "style": {
                    "width": "data(weight)",
                },
            },
            {
                "selector": ".top-center",
                "style": {
                    "text-valign": "top",
                    "text-halign": "center",
                    "font-size": "20px",
                },
            },
        ],
        elements=elements,
    )

    return cytoscape_graph


# TODO: temporary workaround for cannot create edge for non-existence source or target
# https://github.com/plotly/dash-cytoscape/issues/106
def generate_new_id(graph_json):
    id_map = {}
    # Give new id to each node
    for node in graph_json["elements"]["nodes"]:
        new_id = str(uuid.uuid4())
        old_id = node["data"]["id"]
        id_map[old_id] = new_id
        node["data"]["id"] = new_id

    # Update parent node id
    for node in graph_json["elements"]["nodes"]:
        if (old_parent_id := node["data"]["parent"]) is not None:
            node["data"]["parent"] = id_map[old_parent_id]

    # Update source and target for each edge
    for edge in graph_json["elements"]["edges"]:
        edge["data"]["source"] = id_map[edge["data"]["source"]]
        edge["data"]["target"] = id_map[edge["data"]["target"]]

    return graph_json


def callbacks(app):
    @app.callback(
        Output("progress", "value"),
        Output("progress", "max"),
        Output("progress", "label"),
        Output("progress-status", "children"),
        Input("cy-graph", "children"),
        State("progress-status", "children"),
        running=[(Input("submit-button", "disabled"), True, False)],
        prevent_initial_call=True,
    )
    def plot_cytoscape_graph(graph_children, progress):
        if graph_children is not None:
            return 1, 1, "1/1", "Done"
        else:
            return 1, 1, "", progress

    @app.callback(
        Output("cy-graph", "children"),
        Output("is-new-graph", "data", allow_duplicate=True),
        Output("memory-node-degree", "data"),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Input("node-degree", "value"),
        Input("graph-cut-weight", "value"),
        State("memory-node-degree", "data"),
        State("memory-graph-cut-weight", "data"),
        State("cy-graph-container", "style"),
        State("graph-layout", "value"),
        State("is-new-graph", "data"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def update_graph(
        new_node_degree,
        new_cut_weight,
        old_node_degree,
        old_cut_weight,
        container_style,
        graph_layout,
        is_new_graph,
        savepath,
    ):
        if container_style["visibility"] == "hidden":
            cy_graph = generate_cytoscape_js_network(graph_layout, None)
            return cy_graph, False, new_node_degree, new_cut_weight

        if new_node_degree is None:
            new_node_degree = old_node_degree

        conditions = (
            is_new_graph or new_cut_weight != old_cut_weight or new_node_degree != old_node_degree
        )
        if conditions:
            G = rebuild_graph(
                new_node_degree,
                new_cut_weight,
                format="html",
                with_layout=True,
                graph_path=savepath["graph"],
            )
            graph_json = create_cytoscape_js(G, style="dash")
            graph_json = generate_new_id(graph_json)
            cy_graph = generate_cytoscape_js_network(graph_layout, graph_json)
            return cy_graph, False, new_node_degree, new_cut_weight
        else:
            return no_update, False, new_node_degree, new_cut_weight

    @app.callback(
        Output("cy", "layout"),
        Output("cy", "elements", allow_duplicate=True),
        Input("graph-layout", "value"),
        State("node-degree", "value"),
        State("graph-cut-weight", "value"),
        State("cy", "elements"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def update_graph_layout(layout, node_degree, weight, elements, savepath):
        if layout == "preset":
            G = rebuild_graph(
                node_degree, weight, format="html", with_layout=True, graph_path=savepath["graph"]
            )
            graph_json = create_cytoscape_js(G, style="dash")
            graph_json = generate_new_id(graph_json)
            elements = [*graph_json["elements"]["nodes"], *graph_json["elements"]["edges"]]

        return {"name": layout}, elements

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="show_edge_info"),
        Output("edge-info-container", "style"),
        Output("edge-info", "children"),
        Input("cy", "selectedEdgeData"),
        State("cy", "tapEdgeData"),
        State("pmid-title-dict", "data"),
        prevent_initial_call=True,
    )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="show_node_info"),
        Output("node-info-container", "style"),
        Output("node-info", "children"),
        Input("cy", "selectedNodeData"),
        State("cy", "tapNodeData"),
        State("pmid-title-dict", "data"),
        prevent_initial_call=True,
    )
