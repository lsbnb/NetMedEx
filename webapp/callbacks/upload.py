from __future__ import annotations

from dash import Input, Output, State, html

from webapp.upload_limits import (
    MAX_GRAPH_UPLOAD_BYTES,
    MAX_PMID_UPLOAD_BYTES,
    MAX_PUBTATOR_UPLOAD_BYTES,
    UploadSizeError,
    decode_upload_text,
    validate_upload_size,
)


def display_uploaded_data(data, filename, *, max_bytes, label):
    if data is not None:
        try:
            _, decoded_content = decode_upload_text(data, max_bytes=max_bytes, label=label)
        except (UploadSizeError, ValueError) as exc:
            return [
                html.H6(f"File: {filename}", style={"marginBottom": "5px", "marginTop": "5px"}),
                html.Div(str(exc), className="text-danger small"),
            ]
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
        return display_uploaded_data(
            upload_data,
            filename,
            max_bytes=MAX_PMID_UPLOAD_BYTES,
            label="PMID list",
        )

    @app.callback(
        Output("pubtator-file-upload", "children"),
        Input("pubtator-file-data", "contents"),
        State("pubtator-file-data", "filename"),
    )
    def update_pubtator_upload(pubtator_data, filename):
        return display_uploaded_data(
            pubtator_data,
            filename,
            max_bytes=MAX_PUBTATOR_UPLOAD_BYTES,
            label="PubTator/BioC-JSON file",
        )

    @app.callback(
        Output("graph-file-upload", "children"),
        Input("graph-file-data", "contents"),
        State("graph-file-data", "filename"),
    )
    def update_graph_file_upload(graph_data, filename):
        if graph_data is not None:
            try:
                validate_upload_size(
                    graph_data,
                    max_bytes=MAX_GRAPH_UPLOAD_BYTES,
                    label="Graph pickle",
                )
            except (UploadSizeError, ValueError) as exc:
                return [
                    html.H6(
                        f"File: {filename}",
                        style={"marginBottom": "5px", "marginTop": "5px"},
                    ),
                    html.Div(str(exc), className="text-danger small"),
                ]
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
