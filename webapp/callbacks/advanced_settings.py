import dash
from dash import Input, Output, State


def callbacks(app):
    @app.callback(
        Output("advanced-settings-collapse", "style"),
        Output("max-edges", "tooltip"),
        Output("max-articles", "tooltip"),
        Input("advanced-settings-btn", "n_clicks"),
        State("advanced-settings-collapse", "style"),
        prevent_initial_call=True,
    )
    def open_advanced_options(n_clicks, style):
        if n_clicks is None:
            return dash.no_update

        # Get current visibility from style
        current_visibility = style.get("visibility", "hidden")

        # Toggle visibility
        if current_visibility == "hidden":
            new_visibility = "visible"
            tooltip_visible = True
        else:
            new_visibility = "hidden"
            tooltip_visible = False

        return (
            {"visibility": new_visibility},
            {"placement": "bottom", "always_visible": tooltip_visible},
            {"placement": "bottom", "always_visible": tooltip_visible},
        )
