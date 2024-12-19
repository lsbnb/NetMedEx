from dash import Input, Output, State

from webapp.utils import visibility


def callbacks(app):
    @app.callback(
        Output("graph-settings-collapse", "style", allow_duplicate=True),
        Output("graph-cut-weight", "tooltip"),
        Input("graph-settings-btn", "n_clicks"),
        State("graph-settings-collapse", "style"),
        prevent_initial_call=True,
    )
    def open_graph_settings(n_clicks, style):
        visibility = style["visibility"]
        toggle = {"hidden": "visible", "visible": "hidden"}
        weight_toggle = {"hidden": True, "visible": False}
        return (
            {"visibility": toggle[visibility]},
            {"placement": "bottom", "always_visible": weight_toggle[visibility]},
        )

    @app.callback(
        Output("graph-settings-collapse", "style", allow_duplicate=True),
        Output("graph-cut-weight", "value"),
        Output("graph-cut-weight", "tooltip", allow_duplicate=True),
        Output("download-pubtator-btn", "style"),
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
        return (
            visibility.hidden,
            cut_weight,
            {"placement": "bottom", "always_visible": False},
            pubtator_btn_visibility,
        )
