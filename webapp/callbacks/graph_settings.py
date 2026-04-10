from __future__ import annotations

from dash import Input, Output, State, no_update
from webapp.utils import display

hidden_panel_style = {
    "position": "absolute",
    "top": "-9999px",
    "left": "-9999px",
    "visibility": "hidden",
    "height": "0px",
    "width": "100%",
    "overflow": "hidden",
}
visible_panel_style = {"display": "block"}


def callbacks(app):
    @app.callback(
        Output("stat-articles", "children"),
        Output("stat-nodes", "children"),
        Output("stat-edges", "children"),
        Input("cy", "selectedNodeData"),
        Input("cy", "selectedEdgeData"),
        Input("cy", "elements"),
    )
    def update_network_statistics(selected_nodes, selected_edges, elements):
        if not elements:
            return "0", "0", "0"

        # Calculate total directly from current elements on screen
        total_nodes = 0
        total_edges = 0
        total_article_pmids = set()

        for ele in elements:
            data = ele.get("data", {})
            if "source" in data and "target" in data:
                total_edges += 1
                edge_pmids = data.get("pmids", [])
                if isinstance(edge_pmids, list):
                    total_article_pmids.update(edge_pmids)
                elif isinstance(edge_pmids, str):
                    total_article_pmids.add(edge_pmids)
            else:
                total_nodes += 1
                node_pmids = data.get("pmids", [])
                if isinstance(node_pmids, list):
                    total_article_pmids.update(node_pmids)
                elif isinstance(node_pmids, str):
                    total_article_pmids.add(node_pmids)

        total_articles = len(total_article_pmids)

        articles_text = str(total_articles)
        nodes_text = str(total_nodes)
        edges_text = str(total_edges)

        # Check if we have selection
        has_selection = (selected_nodes and len(selected_nodes) > 0) or (
            selected_edges and len(selected_edges) > 0
        )

        if has_selection:
            # Count selected nodes
            n_selected_nodes = len(selected_nodes) if selected_nodes else 0
            if n_selected_nodes > 0:
                nodes_text = f"{total_nodes} ({n_selected_nodes} selected)"

            # Count selected edges
            n_selected_edges = len(selected_edges) if selected_edges else 0
            if n_selected_edges > 0:
                edges_text = f"{total_edges} ({n_selected_edges} selected)"

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
                    articles_text = f"{total_articles} ({n_selected_articles} selected)"

        return articles_text, nodes_text, edges_text

    @app.callback(
        Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
        Input("cy", "elements"),
        Input("cy-graph-container", "style"),
        State("sidebar-panel-toggle", "active_tab"),
        prevent_initial_call=True,
    )
    def switch_to_graph_panel(elements, container_style, current_value):
        # Only auto-switch to graph if we are currently in search mode,
        # graph becomes visible, and we actually HAVE elements to show.
        if (
            current_value == "search"
            and container_style
            and container_style.get("visibility") == "visible"
            and elements
            and len(elements) > 0
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
        if not toggle_value:
            return no_update

        if toggle_value == "graph":
            return (
                hidden_panel_style,
                visible_panel_style,
                hidden_panel_style,
                "sidebar graph-mode",
            )
        elif toggle_value == "chat":
            return hidden_panel_style, hidden_panel_style, visible_panel_style, "sidebar chat-mode"

        # Explicitly handle 'search' case
        if toggle_value == "search":
            return visible_panel_style, hidden_panel_style, hidden_panel_style, "sidebar"

        return no_update

    @app.callback(
        [
            Output("graph-cut-weight", "min"),
            Output("graph-cut-weight", "max"),
            Output("graph-cut-weight", "step"),
            Output("graph-cut-weight", "marks"),
            Output("graph-cut-weight", "value", allow_duplicate=True),
            Output("edge-weight-cutoff-label", "children"),
            Output("edge-weight-cutoff-label-tooltip", "data-tooltip"),
        ],
        Input("weighting-method", "value"),
        prevent_initial_call="initial_duplicate",
    )
    def update_weight_cutoff_range(weighting_method):
        if weighting_method == "npmi":
            # NPMI range 0 to 1
            tooltip_text = (
                "Filter edges by NPMI score (0.0-1.0):\n"
                "• 0.3 - 0.5 (Broad Association): Common comorbidities or standard therapies\n"
                "• 0.5 - 0.8 (Specific Association): Precise mechanisms (e.g. target proteins)\n"
                "• 0.8 - 1.0 (Strong Coupling): Medical definitions or rare findings"
            )
            return (
                0,
                1,
                0.1,
                {0: "0", 0.5: "0.5", 1: "1.0"},
                [0.3, 1.0],
                "Edge Weight Cutoff (NPMI)",
                tooltip_text,
            )
        else:
            # Default (Frequency)
            # Range 0 to 20
            tooltip_text = (
                "Filter edges by co-occurrence frequency (0-20):\n"
                "• Values are scaled to 0-20 relative to the maximum co-occurrence count.\n"
                "• Note: If max frequency > 20, values are scaled proportionally."
            )
            return (
                0,
                20,
                1,
                {i: str(i) for i in range(0, 21, 5)},
                [0, 20],
                "Edge Weight Cutoff (Frequency)",
                tooltip_text,
            )

    @app.callback(
        Output("fcose-repulsion-wrapper", "style"),
        Input("graph-layout", "value"),
    )
    def toggle_repulsion_slider(layout):
        """Show Node Repulsion slider only when fcose is selected."""
        if layout == "fcose":
            return display.block
        return display.hidden_panel

    @app.callback(
        Output("edge-weight-cutoff-wrapper", "style"),
        Output("confidence-threshold-wrapper", "style"),
        Input("edge-method", "value"),
    )
    def toggle_edge_filtering_visibility(edge_method):
        """Show appropriate filter based on construction method."""
        if edge_method == "semantic":
            return display.hidden_panel, display.block
        elif edge_method == "co-occurrence":
            return display.block, display.hidden_panel
        # Default (relation or mixed) -> hide both as they don't apply directly
        return display.hidden_panel, display.hidden_panel
