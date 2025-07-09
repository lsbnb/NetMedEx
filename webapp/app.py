from dotenv import load_dotenv

load_dotenv()

import os

import dash_bootstrap_components as dbc
import diskcache
from dash import ClientsideFunction, Dash, Input, Output, dcc, html
from dash.long_callback import DiskcacheLongCallbackManager

from netmedex.utils import config_logger
from webapp.callbacks import collect_callbacks
from webapp.utils import cleanup_tempdir

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"))


cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    long_callback_manager=long_callback_manager,
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
        app.run(host=os.getenv("HOST", "127.0.0.1"), port=os.getenv("PORT", "8050"))
    finally:
        cleanup_tempdir()


if __name__ == "__main__":
    main()
