from __future__ import annotations

from dash import Input, Output, State, no_update

from webapp.utils import display


def callbacks(app):
    @app.callback(
        Output("graph-cut-weight", "value"),
        Input("cy-graph-container", "style"),
        State("memory-graph-cut-weight", "data"),
        State("api-toggle-items", "value"),
        # prevent_initial_call=True,
    )
    def update_graph_params(container_style, cut_weight, api_or_file):
        return cut_weight

    @app.callback(
        Output("stat-articles", "children"),
        Output("stat-nodes", "children"),
        Output("stat-edges", "children"),
        Input("cy", "selectedNodeData"),
        Input("cy", "selectedEdgeData"),
        Input("total-stats", "data"),
    )
    def update_network_statistics(selected_nodes, selected_edges, total_stats):
        if not total_stats:
            return "0", "0", "0"

        # Default to total counts
        articles_text = str(total_stats.get("articles", 0))
        nodes_text = str(total_stats.get("nodes", 0))
        edges_text = str(total_stats.get("edges", 0))

        # Check if we have selection
        has_selection = (selected_nodes and len(selected_nodes) > 0) or (
            selected_edges and len(selected_edges) > 0
        )

        if has_selection:
            # Count selected nodes
            n_selected_nodes = len(selected_nodes) if selected_nodes else 0
            if n_selected_nodes > 0:
                nodes_text = f"{total_stats['nodes']} ({n_selected_nodes} selected)"

            # Count selected edges
            n_selected_edges = len(selected_edges) if selected_edges else 0
            if n_selected_edges > 0:
                edges_text = f"{total_stats['edges']} ({n_selected_edges} selected)"

            # Count selected articles (unique PMIDs from selected edges)
            if selected_edges:
                pmids = set()
                for edge in selected_edges:
                    if "pmids" in edge:
                        edge_pmids = edge["pmids"]
                        if isinstance(edge_pmids, list):
                            pmids.update(edge_pmids)
                        elif isinstance(edge_pmids, str):
                            pmids.add(edge_pmids)

                n_selected_articles = len(pmids)
                if n_selected_articles > 0:
                    articles_text = f"{total_stats['articles']} ({n_selected_articles} selected)"

        return articles_text, nodes_text, edges_text

    @app.callback(
        Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
        Input("cy-graph-container", "style"),
        State("sidebar-panel-toggle", "active_tab"),
        prevent_initial_call=True,
    )
    def switch_to_graph_panel(container_style, current_value):
        # Only auto-switch to graph if we are currently in search mode and graph becomes visible
        if (
            current_value == "search"
            and container_style
            and container_style.get("visibility") == "visible"
        ):
            return "graph"
        return no_update

    @app.callback(
        Output("search-panel", "style"),
        Output("graph-settings-panel", "style"),
        Output("chat-panel-container", "style"),
        Output("sidebar-container", "className"),
        Input("sidebar-panel-toggle", "active_tab"),
    )
    def toggle_panels(toggle_value):
        print(f"DEBUG: toggle_panels triggered with value: {toggle_value}")
        if toggle_value == "graph":
            return display.none, display.block, display.none, "sidebar graph-mode"
        elif toggle_value == "chat":
            return display.none, display.none, display.block, "sidebar chat-mode"
        # search (default)
        return display.block, display.none, display.none, "sidebar"

    @app.callback(
        [
            Output("graph-cut-weight", "min"),
            Output("graph-cut-weight", "max"),
            Output("graph-cut-weight", "step"),
            Output("graph-cut-weight", "marks"),
            Output("graph-cut-weight", "value", allow_duplicate=True),
            Output("edge-weight-cutoff-label", "children"),
        ],
        Input("weighting-method", "value"),
        prevent_initial_call=True,
    )
    def update_weight_cutoff_range(weighting_method):
        if weighting_method == "npmi":
            # NPMI range 0 to 1
            return (
                0,
                1,
                0.1,
                {0: "0", 0.5: "0.5", 1: "1.0"},
                [0.3, 1.0],
                "Edge Weight Cutoff (NPMI)",
            )
        else:
            # Default (Frequency)
            # Range 0 to 20
            return (
                0,
                20,
                1,
                {i: str(i) for i in range(0, 21, 5)},
                [0, 20],
                "Edge Weight Cutoff (Frequency)",
            )
