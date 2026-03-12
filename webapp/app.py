from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import diskcache
from dash import ClientsideFunction, Dash, DiskcacheManager, Input, Output, dcc, html

from netmedex.utils import config_logger
from webapp.callbacks import collect_callbacks
from webapp.utils import cleanup_tempdir

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"))

# Load external layout extensions (fCose, CoSE-Bilkent, etc.)
cyto.load_extra_layouts()

cache = diskcache.Cache("./cache")
background_callback_manager = DiskcacheManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    background_callback_manager=background_callback_manager,
    suppress_callback_exceptions=True,
)
app.title = "NetMedEx"
app._favicon = "NetMedEx_ico.ico"

from webapp.components.graph import graph
from webapp.components.sidebar import sidebar

current_session_path = dcc.Store(id="current-session-path")

content = html.Div(
    [current_session_path, sidebar, graph],
    className="d-flex flex-row position-relative h-100",
)

app.layout = html.Div([content, html.Div(id="post-js-scripts")], id="main-container")


def main():
    try:
        collect_callbacks(app)
        app.clientside_callback(
            ClientsideFunction(namespace="clientside", function_name="info_scroll"),
            Output("post-js-scripts", "children"),
            Input("post-js-scripts", "id"),
        )
        # Provide user-friendly access instructions
        host = os.getenv("HOST", "127.0.0.1")
        port = os.getenv("PORT", "8050")

        print("\n" + "=" * 50)
        print("NetMedEx Web Application Starting...")
        if host == "0.0.0.0":
            print(f"Listening on all interfaces (0.0.0.0:{port})")
            print(f"👉 To access the app, open: http://localhost:{port}")
        else:
            print(f"👉 Access the app at: http://{host}:{port}")
        print("=" * 50 + "\n")

        app.run(
            host=host,
            port=port,
            debug=(os.getenv("FLASK_DEBUG") == "true"),
        )
    finally:
        cleanup_tempdir()


if __name__ == "__main__":
    main()
