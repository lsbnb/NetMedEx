import base64

from dash import Input, Output, State, html, no_update


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
        return no_update


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
