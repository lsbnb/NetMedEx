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

    @app.callback(
        Output("chat-override-fields-container", "style"),
        Input("chat-model-override-toggle", "value"),
    )
    def toggle_chat_override_fields(override_toggle):
        """Show the Chat Model override fields only when that toggle is enabled"""
        if "enabled" in (override_toggle or []):
            return display.block
        return display.none

    def _progressive_disclosure_styles(selected_provider, main_provider):
        """Shared visibility logic for the "Chat Model Override" and "Verifier
        Provider" sections: only ask for a separate API key when the user has
        actually picked a provider different from their main one (an empty
        selection means "same as main provider"); only ask for a Base URL when
        the effective provider is Local Ollama.
        """
        selected = (selected_provider or "").strip().lower()
        main = (main_provider or "openai").strip().lower()
        effective = selected or main
        api_key_style = display.block if selected and selected != main else display.none
        base_url_style = display.block if effective == "local" else display.none
        return api_key_style, base_url_style

    @app.callback(
        [
            Output("chat-override-api-key-row", "style"),
            Output("chat-override-base-url-row", "style"),
        ],
        [
            Input("chat-override-provider", "value"),
            Input("llm-provider-selector", "value"),
        ],
    )
    def toggle_chat_override_extra_fields(override_provider, main_provider):
        return _progressive_disclosure_styles(override_provider, main_provider)

    @app.callback(
        [
            Output("relation-verifier-api-key-row", "style"),
            Output("relation-verifier-base-url-row", "style"),
        ],
        [
            Input("relation-verifier-provider", "value"),
            Input("llm-provider-selector", "value"),
        ],
    )
    def toggle_relation_verifier_extra_fields(verifier_provider, main_provider):
        return _progressive_disclosure_styles(verifier_provider, main_provider)
