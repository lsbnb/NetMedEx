from dash import Input, Output, State


def callbacks(app):
    @app.callback(
        Output("advanced-settings-collapse", "style", allow_duplicate=True),
        Output("max-edges", "tooltip"),
        Output("max-articles", "tooltip"),
        Input("advanced-settings-btn", "n_clicks"),
        State("advanced-settings-collapse", "style"),
        prevent_initial_call=True,
    )
    def open_advanced_options(n_clicks, style):
        visibility = style["visibility"]
        toggle = {"hidden": "visible", "visible": "hidden"}
        weight_toggle = {"hidden": True, "visible": False}
        return (
            {"visibility": toggle[visibility]},
            {"placement": "bottom", "always_visible": weight_toggle[visibility]},
            {"placement": "bottom", "always_visible": weight_toggle[visibility]},
        )
