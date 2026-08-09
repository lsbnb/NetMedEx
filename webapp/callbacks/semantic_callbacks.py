from __future__ import annotations

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
        """Show/hide semantic threshold slider based on edge construction method"""
        if edge_method == "semantic":
            return display.block
        return display.none

    @app.callback(
        Output("relation-verifier-provider-container", "style"),
        Input("relation-verification-toggle", "value"),
    )
    def toggle_relation_verifier_provider(verification_toggle):
        """Show the verifier-provider dropdown only when relation verification is enabled"""
        if "enabled" in (verification_toggle or []):
            return display.block
        return display.none
