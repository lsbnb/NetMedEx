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
    try:
        import multiprocess

        multiprocess.set_start_method("spawn", force=True)
    except Exception:
        pass

from dash import ClientsideFunction, Input, Output

from webapp.app import app
from webapp.callbacks import collect_callbacks

# Initialize all callbacks
collect_callbacks(app)

# Initialize clientside callbacks
app.clientside_callback(
    ClientsideFunction(namespace="clientside", function_name="info_scroll"),
    Output("post-js-scripts", "children"),
    Input("post-js-scripts", "id"),
)

# Expose the Flask server for WSGI runners like Gunicorn
application = app.server
