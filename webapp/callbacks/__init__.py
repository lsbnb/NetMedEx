import importlib
from pathlib import Path

from dash import Dash


def collect_callbacks(app: Dash):
    for file in Path(__file__).parent.glob("*.py"):
        if file.stem != "__init__":
            module = importlib.import_module(f".{file.stem}", package=__package__)
            if hasattr(module, "callbacks"):
                module.callbacks(app)
