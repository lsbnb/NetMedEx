import os
from dash import (
    ClientsideFunction,
    Input,
    Output,
    State,
    callback_context,
    clientside_callback,
    no_update,
)

from netmedex.cytoscape_js import create_cytoscape_js
from webapp.callbacks.graph_utils import rebuild_graph


def build_pmid_citation_dict(graph_obj):
    pmid_metadata = graph_obj.graph.get("pmid_metadata", {}) if graph_obj is not None else {}
    return {
        pmid: meta.get("citation_count")
        for pmid, meta in pmid_metadata.items()
        if isinstance(meta, dict)
    }


def get_layout_config(layout_name, node_repulsion=45000):
    """
    Get optimized layout configuration based on layout name.
    Targeting better visualization for compound/community graphs.
    """
    if layout_name == "fcose":
        return {
            "name": "fcose",
            "quality": "default",
            "randomize": True,
            "animate": False,
            "fit": True,
            "padding": 30,
            "nodeSeparation": 75,
            "nodeRepulsion": node_repulsion,
            "idealEdgeLength": 50,
            "edgeElasticity": 0.45,
            "nestingFactor": 0.1,
            "numIter": 2500,
            "tile": True,
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
        Output("cy", "layout", allow_duplicate=True),
        Input("graph-reset-view-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_graph_view(n_clicks):
        if not n_clicks:
            return no_update

        # Reset Graph View should restore the viewport/layout,
        # not rebuild graph elements from backend.
        # Use preset+fit to zoom/pan back to the full current graph state.
        return {"name": "preset", "fit": True, "padding": 30, "animate": False}

    @app.callback(
        Output("progress", "value", allow_duplicate=True),
        Output("progress", "max"),
        Output("progress", "label", allow_duplicate=True),
        Output("progress-status", "children", allow_duplicate=True),
        Input("cy", "elements"),
        State("progress-status", "children"),
        prevent_initial_call=True,
    )
    def plot_cytoscape_graph(elements, progress):
        if elements:
            return 1, 1, "1/1", "Done"
        else:
            return 0, 1, "", ""

    clientside_callback(
        """
        function(is_disabled) {
            if (is_disabled) {
                // Return empty style to effectively hide the graph while keeping it technically mounted
                return {"visibility": "hidden", "height": "400px"};
            }
            // Once the search is done, the button is re-enabled. Unhide the graph.
            return {"visibility": "visible", "height": "800px"};
        }
        """,
        Output("cy-graph-container", "style", allow_duplicate=True),
        Input("submit-button", "disabled"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("cy", "elements"),
        Output("cy", "layout"),
        Output("is-new-graph", "data", allow_duplicate=True),
        Output("memory-node-degree", "data"),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("memory-cy-params", "data"),
        Output("memory-graph-layout", "data"),
        Output("memory-fcose-node-repulsion", "data"),
        Output("pmid-citation-dict", "data", allow_duplicate=True),
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
        triggered = [t["prop_id"] for t in callback_context.triggered]
        print(f"DEBUG: update_graph triggered by {triggered}")

        # Normalization
        if cy_params is None:
            cy_params = []
        if old_cy_params is None:
            old_cy_params = []
        if new_node_degree is None:
            new_node_degree = old_node_degree if old_node_degree is not None else 1
        if new_cut_weight is None:
            new_cut_weight = old_cut_weight if old_cut_weight is not None else [0, 20]

        if not savepath or not savepath.get("graph"):
            return (
                no_update,
                no_update,
                False,
                new_node_degree,
                new_cut_weight,
                cy_params,
                graph_layout,
                node_repulsion,
                no_update,
            )

        show_community = "community" in cy_params

        # Use cutoff directly; backend already handles scaling mapping
        effective_cut_weight = new_cut_weight

        # Check triggers
        rebuild_needed = (
            is_new_graph
            or new_cut_weight != old_cut_weight
            or new_node_degree != old_node_degree
            or set(cy_params) != set(old_cy_params)
        )
        layout_changed = graph_layout != old_layout or node_repulsion != old_repulsion

        # Avoid redundant reset cycles
        if (
            triggered == ["is-new-graph.data"]
            and not is_new_graph
            and not rebuild_needed
            and not layout_changed
        ):
            return (
                no_update,
                no_update,
                False,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if rebuild_needed or layout_changed:
            try:
                # Defensive check: Ensure graph path exists before trying to load it
                graph_path = savepath.get("graph")
                if not graph_path or not os.path.exists(graph_path):
                    print(f"ERROR: Graph file missing at {graph_path}. Session may have expired.")
                    # Return a clear error state for elements to trigger a potential UI alert
                    return (
                        [],  # Clear elements
                        no_update,
                        False,
                        new_node_degree,
                        new_cut_weight,
                        cy_params,
                        graph_layout,
                        node_repulsion,
                        no_update,
                    )

                G = rebuild_graph(
                    new_node_degree,
                    effective_cut_weight,
                    format="html",
                    with_layout=True,
                    graph_path=graph_path,
                    community=show_community,
                    weighting_method=weighting_method,
                )

                graph_json = create_cytoscape_js(G, style="dash")
                if G.graph.get("is_pruned"):
                    print(
                        f"WARNING: Graph was pruned for performance. Final Elements: {len(graph_json['elements']['nodes'])} nodes, {len(graph_json['elements']['edges'])} edges"
                    )

                elements = [*graph_json["elements"]["nodes"], *graph_json["elements"]["edges"]]
                layout_config = get_layout_config(graph_layout, node_repulsion)
                pmid_citation_dict = build_pmid_citation_dict(G)

                # Ensure elements is at least an empty list, not None
                if elements is None:
                    elements = []

                return (
                    elements,
                    layout_config,
                    False,
                    new_node_degree,
                    new_cut_weight,
                    cy_params,
                    graph_layout,
                    node_repulsion,
                    pmid_citation_dict,
                )
            except Exception as e:
                print(f"ERROR in update_graph: {e}")
                import traceback

                traceback.print_exc()
                return (
                    no_update,
                    no_update,
                    False,
                    new_node_degree,
                    new_cut_weight,
                    cy_params,
                    graph_layout,
                    node_repulsion,
                    no_update,
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
            no_update,
        )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="show_edge_info"),
        Output("edge-info-container", "style"),
        Output("edge-info", "children"),
        Input("cy", "selectedEdgeData"),
        State("cy", "tapEdgeData"),
        State("pmid-title-dict", "data"),
        State("pmid-citation-dict", "data"),
        prevent_initial_call=True,
    )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="show_node_info"),
        Output("node-info-container", "style"),
        Output("node-info", "children"),
        Input("cy", "selectedNodeData"),
        State("cy", "tapNodeData"),
        State("pmid-title-dict", "data"),
        State("pmid-citation-dict", "data"),
        prevent_initial_call=True,
    )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="apply_graph_visual_filters"),
        Output("cy", "stylesheet"),
        Input("confidence-threshold", "value"),
        Input("graph-node-search", "value"),
        Input("graph-visible-node-types", "value"),
        Input("cy", "elements"),
        State("cy", "stylesheet"),
        prevent_initial_call=False,
    )
