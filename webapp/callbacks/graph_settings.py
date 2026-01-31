from __future__ import annotations

from dash import Input, Output, State

from webapp.utils import display, visibility


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
        Output("sidebar-panel-toggle", "active_tab"),
        Input("cy-graph-container", "style"),
        State("sidebar-panel-toggle", "active_tab"),
        prevent_initial_call=True,
    )
    def switch_to_graph_panel(container_style, current_value):
        if container_style.get("visibility") == "visible":
            return "graph"
        return current_value

    @app.callback(
        Output("search-panel", "style"),
        Output("graph-settings-panel", "style"),
        Output("chat-panel-container", "style"),
        Output("sidebar-container", "className"),
        Input("sidebar-panel-toggle", "active_tab"),
    )
    def toggle_panels(toggle_value):
        if toggle_value == "graph":
            return display.none, display.block, display.none, "sidebar graph-mode"
        elif toggle_value == "chat":
            return display.none, display.none, display.block, "sidebar chat-mode"
        # search (default)
        return display.block, display.none, display.none, "sidebar"
