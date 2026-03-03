import dash_cytoscape as cyto
from dash import ClientsideFunction, Input, Output, State, clientside_callback, no_update

from netmedex.cytoscape_js import create_cytoscape_js
from webapp.callbacks.graph_utils import rebuild_graph


def get_layout_config(layout_name, node_repulsion=45000):
    """
    Get optimized layout configuration based on layout name.
    Targeting better visualization for compound/community graphs.
    """
    if layout_name == "fcose":
        return {
            "name": "fcose",
            "quality": "default",  # "proof" is more thorough but slower
            "randomize": True,
            "animate": False,  # skip animation for large graphs
            "fit": True,
            "padding": 30,
            "nodeSeparation": 75,
            "nodeRepulsion": node_repulsion,
            "idealEdgeLength": 50,
            "edgeElasticity": 0.45,
            "nestingFactor": 0.1,
            "numIter": 2500,
            "tile": True,  # spread disconnected components
            "tilingPaddingVertical": 10,
            "tilingPaddingHorizontal": 10,
        }
    if layout_name == "cose":
        return {
            "name": "cose",
            "idealEdgeLength": 50,
            "nodeOverlap": 20,
            "refresh": 20,
            "fit": True,
            "padding": 30,
            "randomize": False,
            "componentSpacing": 40,
            "nodeRepulsion": 10000,
            "edgeElasticity": 100,
            "nestingFactor": 1.2,
            "gravity": 0.5,
            "numIter": 1000,
            "initialTemp": 200,
            "coolingFactor": 0.95,
            "minTemp": 1.0,
        }
    return {"name": layout_name}


def callbacks(app):
    @app.callback(
        Output("progress", "value", allow_duplicate=True),
        Output("progress", "max"),
        Output("progress", "label", allow_duplicate=True),
        Output("progress-status", "children", allow_duplicate=True),
        Input("cy", "elements"),
        State("progress-status", "children"),
        running=[(Input("submit-button", "disabled"), True, False)],
        prevent_initial_call=True,
    )
    def plot_cytoscape_graph(elements, progress):
        if elements:
            return 1, 1, "1/1", "Done"
        else:
            return 0, 1, "", ""

    @app.callback(
        Output("cy", "elements"),
        Output("cy", "layout"),
        Output("is-new-graph", "data", allow_duplicate=True),
        Output("memory-node-degree", "data"),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("memory-cy-params", "data"),
        Output("memory-graph-layout", "data"),
        Output("memory-fcose-node-repulsion", "data"),
        Input("is-new-graph", "data"),
        Input("graph-layout", "value"),
        Input("node-degree", "value"),
        Input("graph-cut-weight", "value"),
        Input("cy-params", "value"),
        Input("fcose-node-repulsion", "value"),
        State("memory-node-degree", "data"),
        State("memory-graph-cut-weight", "data"),
        State("memory-cy-params", "data"),
        State("memory-graph-layout", "data"),
        State("memory-fcose-node-repulsion", "data"),
        State("cy-graph-container", "style"),
        State("current-session-path", "data"),
        State("weighting-method", "value"),
        prevent_initial_call=True,
    )
    def update_graph(
        is_new_graph,
        graph_layout,
        new_node_degree,
        new_cut_weight,
        cy_params,
        node_repulsion,
        old_node_degree,
        old_cut_weight,
        old_cy_params,
        old_layout,
        old_repulsion,
        container_style,
        savepath,
        weighting_method,
    ):
        print(
            f"DEBUG: update_graph triggered! is_new_graph={is_new_graph}, layout={graph_layout}, repulsion={node_repulsion}"
        )

        if not savepath or not savepath.get("graph"):
            print("DEBUG: No graph path found, skipping update.")
            return (
                no_update,
                no_update,
                False,
                new_node_degree,
                new_cut_weight,
                cy_params,
                graph_layout,
                node_repulsion,
            )

        if container_style.get("visibility") == "hidden":
            print("DEBUG: Graph container is hidden, skipping update.")
            return (
                no_update,
                no_update,
                False,
                new_node_degree,
                new_cut_weight,
                cy_params,
                graph_layout,
                node_repulsion,
            )

        if new_node_degree is None:
            new_node_degree = old_node_degree

        # Check if community display is enabled
        show_community = "community" in cy_params if cy_params else False

        # Scale cutoff if using NPMI
        if weighting_method == "npmi":
            effective_cut_weight = (
                [x * 20 for x in new_cut_weight]
                if isinstance(new_cut_weight, list)
                else new_cut_weight * 20
            )
        else:
            effective_cut_weight = new_cut_weight

        # Conditions to REBUILD the graph elements (data filter changed)
        rebuild_needed = (
            is_new_graph
            or new_cut_weight != old_cut_weight
            or new_node_degree != old_node_degree
            or cy_params != old_cy_params
        )

        # Conditions to just update the LAYOUT (no data change, but layout params changed)
        layout_changed = graph_layout != old_layout or node_repulsion != old_repulsion

        if rebuild_needed or layout_changed:
            print(
                f"DEBUG: Updating graph structure. rebuild={rebuild_needed}, layout_change={layout_changed}"
            )
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

            elements = [*graph_json["elements"]["nodes"], *graph_json["elements"]["edges"]]
            layout_config = get_layout_config(graph_layout, node_repulsion)

            print(f"DEBUG: returning {len(elements)} elements")
            return (
                elements,
                layout_config,
                False,
                new_node_degree,
                new_cut_weight,
                cy_params,
                graph_layout,
                node_repulsion,
            )

        return (
            no_update,
            no_update,
            False,
            new_node_degree,
            new_cut_weight,
            cy_params,
            graph_layout,
            node_repulsion,
        )

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
