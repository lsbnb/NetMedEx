from dash import Input, Output

from webapp.utils import visibility


def callbacks(app):
    @app.callback(
        Output("data-input", "value"),
        Output("pmid-file-data", "contents"),
        Output("pubtator-file-data", "contents"),
        Output("input-type-selection", "value"),
        Output("progress", "value", allow_duplicate=True),
        Output("progress", "label", allow_duplicate=True),
        Output("progress-status", "children", allow_duplicate=True),
        Output("output", "children"),
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("reset-button", "n_clicks"),
        Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
        Input("reset-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_inputs(n_clicks):
        # Reset inputs, progress bar, and clear the graph
        # And force return to search tab
        print(f"DEBUG: reset_inputs returning active_tab='search'")
        return "", None, None, "query", 0, "", "", [], visibility.hidden, 0, "search"
