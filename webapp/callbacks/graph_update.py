from __future__ import annotations

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
        boxSelectionEnabled=True,
        style={},
        layout={"name": graph_layout},
        stylesheet=[
            {
                "selector": "core",
                "style": {
                    "selection-box-color": "#FF0000",
                    "selection-box-border-color": "#FF0000",
                    "selection-box-opacity": "0.2",
                },
            },
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
                    "curve-style": "bezier",
                    "label": "data(relation_display)",
                    "font-size": "11px",
                    "font-weight": "bold",
                    "text-background-color": "#ffffff",
                    "text-background-opacity": 0.8,
                    "text-background-padding": "3px",
                    "color": "#000000",
                    "text-rotation": "autorotate",
                },
            },
            {
                "selector": "edge[is_directional]",
                "style": {
                    "target-arrow-shape": "triangle",
                    "target-arrow-color": "#999",
                    "arrow-scale": 1.2,
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
            {
                "selector": ":selected",
                "style": {
                    "overlay-color": "#FF0000",
                    "overlay-opacity": 0.2,
                    "overlay-padding": "5px",
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
        if graph_children:
            # Check for elements to distinguish empty init from actual results
            elements = []
            if isinstance(graph_children, dict):
                # Check for elements in props (standard component structure)
                elements = graph_children.get("props", {}).get("elements", [])
                # Or direct key (if raw dict was passed)
                if not elements:
                    elements = graph_children.get("elements", [])

            # If no elements, reset progress (likely initial empty graph)
            if not elements:
                return 0, 1, "", ""

            return 1, 1, "1/1", "Done"
        else:
            return 0, 1, "", ""

    @app.callback(
        Output("cy-graph", "children"),
        Output("is-new-graph", "data", allow_duplicate=True),
        Output("memory-node-degree", "data"),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("memory-cy-params", "data"),
        Input("node-degree", "value"),
        Input("graph-cut-weight", "value"),
        Input("cy-params", "value"),
        State("memory-node-degree", "data"),
        State("memory-graph-cut-weight", "data"),
        State("memory-cy-params", "data"),
        State("cy-graph-container", "style"),
        State("graph-layout", "value"),
        State("is-new-graph", "data"),
        State("current-session-path", "data"),
        State("weighting-method", "value"),
        prevent_initial_call=True,
    )
    def update_graph(
        new_node_degree,
        new_cut_weight,
        cy_params,
        old_node_degree,
        old_cut_weight,
        old_cy_params,
        container_style,
        graph_layout,
        is_new_graph,
        savepath,
        weighting_method,
    ):
        if container_style["visibility"] == "hidden":
            cy_graph = generate_cytoscape_js_network(graph_layout, None)
            return cy_graph, False, new_node_degree, new_cut_weight, cy_params

        if new_node_degree is None:
            new_node_degree = old_node_degree

        # Check if community display is enabled
        show_community = "community" in cy_params if cy_params else False

        # Scale cutoff if using NPMI (User sees 0~1, Backend uses 0~20)
        # Note: Backend clamps negative NPMI to width 0.
        # So we can just scale by MAX_EDGE_WIDTH (20).
        if weighting_method == "npmi":
            if isinstance(new_cut_weight, list):
                effective_cut_weight = [x * 20 for x in new_cut_weight]
            else:
                effective_cut_weight = new_cut_weight * 20
        else:
            effective_cut_weight = new_cut_weight

        conditions = (
            is_new_graph
            or new_cut_weight != old_cut_weight
            or new_node_degree != old_node_degree
            or cy_params != old_cy_params  # Check if community toggle changed!
        )
        if conditions:
            G = rebuild_graph(
                new_node_degree,
                effective_cut_weight,
                format="html",
                with_layout=True,
                graph_path=savepath["graph"],
                community=show_community,
                weighting_method=weighting_method,
            )
            graph_json = create_cytoscape_js(G, style="dash")
            graph_json = generate_new_id(graph_json)
            cy_graph = generate_cytoscape_js_network(graph_layout, graph_json)
            return cy_graph, False, new_node_degree, new_cut_weight, cy_params
        else:
            return no_update, False, new_node_degree, new_cut_weight, cy_params

    @app.callback(
        Output("cy", "layout"),
        Output("cy", "elements", allow_duplicate=True),
        Input("graph-layout", "value"),
        State("node-degree", "value"),
        State("graph-cut-weight", "value"),
        State("cy", "elements"),
        State("current-session-path", "data"),
        State("weighting-method", "value"),
        prevent_initial_call=True,
    )
    def update_graph_layout(layout, node_degree, weight, elements, savepath, weighting_method):
        if layout == "preset":
            # Scale cutoff if using NPMI
            if weighting_method == "npmi":
                if isinstance(weight, list):
                    effective_weight = [w * 20 for w in weight]
                else:
                    effective_weight = weight * 20
            else:
                effective_weight = weight

            G = rebuild_graph(
                node_degree,
                effective_weight,
                format="html",
                with_layout=True,
                graph_path=savepath["graph"],
                community=False,  # Layout changes don't affect community
                weighting_method=weighting_method,
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
