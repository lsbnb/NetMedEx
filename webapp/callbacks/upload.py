from __future__ import annotations

import base64

from dash import Input, Output, State, html


def display_uploaded_data(data, filename):
    if data is not None:
        content_type, content_string = data.split(",")
        decoded_content = base64.b64decode(content_string).decode("utf-8")
        displayed_text = decoded_content.split("\n")[:5]
        displayed_text = [t[:100] + "..." if len(t) > 100 else t for t in displayed_text]
        return [
            html.H6(f"File: {filename}", style={"marginBottom": "5px", "marginTop": "5px"}),
            html.Pre("\n".join(displayed_text), className="upload-preview"),
        ]
    else:
        return []


def callbacks(app):
    @app.callback(
        Output("output-data-upload", "children"),
        Input("pmid-file-data", "contents"),
        State("pmid-file-data", "filename"),
    )
    def update_data_upload(upload_data, filename):
        return display_uploaded_data(upload_data, filename)

    @app.callback(
        Output("pubtator-file-upload", "children"),
        Input("pubtator-file-data", "contents"),
        State("pubtator-file-data", "filename"),
    )
    def update_pubtator_upload(pubtator_data, filename):
        return display_uploaded_data(pubtator_data, filename)

    @app.callback(
        Output("graph-file-upload", "children"),
        Input("graph-file-data", "contents"),
        State("graph-file-data", "filename"),
    )
    def update_graph_file_upload(graph_data, filename):
        if graph_data is not None:
            return [
                html.H6(
                    f"✅ File ready: {filename}",
                    style={"marginBottom": "5px", "marginTop": "5px", "color": "#28a745"},
                ),
                html.Small(
                    "Click Submit to restore the graph session.",
                    className="text-muted",
                ),
            ]
        return []
