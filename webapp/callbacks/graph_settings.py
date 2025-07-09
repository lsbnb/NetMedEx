from dash import Input, Output, State

from webapp.utils import display, visibility


def callbacks(app):
    @app.callback(
        Output("download-pubtator-btn", "style"),
        Output("graph-cut-weight", "value"),
        Input("cy-graph-container", "style"),
        State("memory-graph-cut-weight", "data"),
        State("api-toggle-items", "value"),
        prevent_initial_call=True,
    )
    def update_graph_params(container_style, cut_weight, api_or_file):
        if api_or_file == "api" and container_style.get("visibility") == "visible":
            pubtator_btn_visibility = visibility.visible
        else:
            pubtator_btn_visibility = visibility.hidden
        return pubtator_btn_visibility, cut_weight

    @app.callback(
        Output("sidebar-panel-toggle", "value"),
        Input("cy-graph-container", "style"),
        State("sidebar-panel-toggle", "value"),
        prevent_initial_call=True,
    )
    def switch_to_graph_panel(container_style, current_value):
        if container_style.get("visibility") == "visible":
            return "graph"
        return current_value

    @app.callback(
        Output("search-panel", "style"),
        Output("graph-settings-panel", "style"),
        Output("sidebar-container", "className"),
        Input("sidebar-panel-toggle", "value"),
    )
    def toggle_panels(toggle_value):
        if toggle_value == "graph":
            return display.none, display.block, "sidebar graph-mode"
        return display.block, display.none, "sidebar"

