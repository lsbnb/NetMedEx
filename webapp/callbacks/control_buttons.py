from dash import Input, Output, State


def callbacks(app):
    @app.callback(
        Output("data-input", "value"),
        Output("pmid-file-data", "contents"),
        Output("pubtator-file-data", "contents"),
        Output("input-type-selection", "value"),
        Output("progress", "value"),
        Output("progress", "label"),
        Output("progress-status", "children", allow_duplicate=True),
        Output("output", "children"),
        Input("reset-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_inputs(n_clicks):
        # Reset to defaults
        # data-input="", pmid-file=None, pubtator-file=None, input-type="query"
        # progress=0, label="", status="", output=""
        return "", None, None, "query", 0, "", "", ""
