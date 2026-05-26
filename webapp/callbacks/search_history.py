from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback_context, html, no_update


def callbacks(app):
    @app.callback(
        Output("search-history-store", "data"),
        Input("submit-button", "n_clicks"),
        State("data-input", "value"),
        State("api-toggle-items", "value"),
        State("search-history-store", "data"),
        prevent_initial_call=True,
    )
    def save_search_history(_, query, source, history):
        if source != "api" or not query or not query.strip():
            return no_update
        query = query.strip()
        history = [q for q in (history or []) if q != query]
        history.insert(0, query)
        return history[:8]

    @app.callback(
        Output("search-history-panel", "children"),
        Input("search-history-store", "data"),
        Input("input-type-selection", "value"),
        prevent_initial_call=False,
    )
    def render_history(history, input_type):
        if not history or input_type != "query":
            return []
        chips = [
            dbc.Button(
                q[:45] + ("…" if len(q) > 45 else ""),
                id={"type": "history-chip", "index": i},
                color="light",
                size="sm",
                className="history-chip",
                title=q,
            )
            for i, q in enumerate(history[:5])
        ]
        return html.Div(
            [
                html.Small(
                    "Recent:",
                    className="text-muted",
                    style={"fontSize": "0.72rem", "whiteSpace": "nowrap"},
                ),
                html.Div(chips, className="d-flex flex-wrap gap-1"),
            ],
            className="d-flex align-items-start gap-2 mt-2",
        )

    @app.callback(
        Output("data-input", "value", allow_duplicate=True),
        Input({"type": "history-chip", "index": ALL}, "n_clicks"),
        State("search-history-store", "data"),
        prevent_initial_call=True,
    )
    def fill_from_history(n_clicks_list, history):
        if not any(n_clicks_list) or not history:
            return no_update
        triggered = callback_context.triggered_id
        if triggered is None:
            return no_update
        idx = triggered.get("index", -1)
        if 0 <= idx < len(history):
            return history[idx]
        return no_update
