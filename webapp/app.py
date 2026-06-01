from __future__ import annotations

import sys

# Force UTF-8 encoding on Windows to prevent ascii codec errors with non-ASCII content
# (e.g. Chinese MeSH terms in graph data, non-ASCII in API responses)
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import multiprocessing

# Set multiprocessing start method to 'spawn' on Linux/macOS to prevent deadlocks in background callbacks
if sys.platform != "win32":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import os

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import diskcache
from dash import ClientsideFunction, Dash, DiskcacheManager, Input, Output, dcc, html

import logging
from netmedex.utils import config_logger
from webapp.callbacks import collect_callbacks
from webapp.utils import cleanup_tempdir

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"), filename="webapp.log")
logger = logging.getLogger(__name__)

# Load external layout extensions (fCose, CoSE-Bilkent, etc.)
cyto.load_extra_layouts()

_cache_path = Path(__file__).parent / "cache"
cache = diskcache.Cache(str(_cache_path))

# Checkpoint the SQLite WAL on startup so stale writes from previous sessions
# don't accumulate into a multi-MB WAL that slows down set_progress() calls.
try:
    import sqlite3 as _sqlite3
    _wal_path = _cache_path / "cache.db"
    if _wal_path.exists():
        _conn = _sqlite3.connect(str(_wal_path))
        _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _conn.close()
        del _conn
    del _sqlite3, _wal_path
except Exception:
    pass

background_callback_manager = DiskcacheManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    background_callback_manager=background_callback_manager,
    suppress_callback_exceptions=True,
    update_title=None,
)
app.title = "NetMedEx"
app._favicon = "NetMedEx_ico.ico"

from webapp.components.graph import graph
from webapp.components.sidebar import sidebar

current_session_path = dcc.Store(id="current-session-path", storage_type="session")

content = html.Div(
    [current_session_path, sidebar, graph],
    className="d-flex flex-row position-relative h-100",
)

app.layout = html.Div([content, html.Div(id="post-js-scripts")], id="main-container")


def main():
    try:
        collect_callbacks(app)

        # Clientside callback to handle info icons scroll positioning
        app.clientside_callback(
            ClientsideFunction(namespace="clientside", function_name="info_scroll"),
            Output("post-js-scripts", "children"),
            Input("post-js-scripts", "id"),
        )
        # Provide user-friendly access instructions
        _host_env = os.getenv("HOST", "127.0.0.1")
        # Conda build environments set HOST to the build triplet (e.g. x86_64-conda-linux-gnu).
        # Fall back to 127.0.0.1 if the value doesn't look like an IP or "0.0.0.0".
        import re as _re
        host = _host_env if _re.match(r"^[\d.]+$", _host_env) else "127.0.0.1"
        # Write back the resolved host so Werkzeug reloader subprocesses inherit the correct value.
        os.environ["HOST"] = host
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
        logger.info(f"NetMedEx started on {host}:{port}")
    finally:
        cleanup_tempdir()


if __name__ == "__main__":
    main()
