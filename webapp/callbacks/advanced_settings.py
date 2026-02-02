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

        # Get current display from style
        current_display = style.get("display", "none")

        # Toggle display
        if current_display == "none":
            new_display = "block"
            tooltip_visible = True
        else:
            new_display = "none"
            tooltip_visible = False

        return (
            {"display": new_display},
            {"placement": "bottom", "always_visible": tooltip_visible},
            {"placement": "bottom", "always_visible": tooltip_visible},
        )
