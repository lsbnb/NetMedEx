"""
Callbacks for semantic edge method UI interactions
"""

from dash import Input, Output

from webapp.utils import display


def callbacks(app):
    """Register callbacks for semantic analysis UI components"""

    @app.callback(
        Output("semantic-options", "style"),
        Input("edge-method", "value"),
    )
    def toggle_semantic_options(edge_method):
        """Show/hide semantic analysis options based on selected edge method"""
        if edge_method == "semantic":
            return display.visible
        return display.none
