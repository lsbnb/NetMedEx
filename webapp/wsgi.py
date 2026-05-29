import multiprocessing
import sys

# Set multiprocessing start method to 'spawn' on Linux/macOS to prevent deadlocks in background callbacks
if sys.platform != "win32":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

from webapp.app import app
from webapp.callbacks import collect_callbacks
from dash import ClientsideFunction, Input, Output

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
