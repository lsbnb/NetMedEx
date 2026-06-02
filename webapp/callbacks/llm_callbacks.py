from __future__ import annotations

import logging
import os
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import requests
from dash import ClientsideFunction, Input, Output, State, html, no_update

from webapp.llm import (
    ANTHROPIC_BASE_URL,
    GEMINI_OPENAI_BASE_URL,
    GROQ_BASE_URL,
    NVIDIA_NIM_BASE_URL,
    OPENAI_BASE_URL,
    OPENROUTER_BASE_URL,
    llm_client,
    normalize_model_for_provider,
)

logger = logging.getLogger(__name__)

STANDARD_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "o1-preview",
    "o1-mini",
    "gpt-3.5-turbo",
]


def _normalize_local_base_url(base_url: str | None) -> str:
    """Normalize Ollama/OpenAI-compatible base URL to include /v1."""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "http://localhost:11434/v1"
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def _sanitize_error_message(message: str) -> str:
    if not message:
        return "Unknown error"
    # Prevent accidental key leakage from URLs like ...?key=XXXX
    if "key=" in message:
        parts = message.split("key=", 1)
        if len(parts) == 2:
            tail = parts[1]
            for sep in ("&", " ", "\n"):
                if sep in tail:
                    tail = tail.split(sep, 1)[1]
                    return f"{parts[0]}key=***{sep}{tail}"
            return f"{parts[0]}key=***"
    return message


def _default_settings() -> dict:
    return {
        "provider": "openai",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "openai_custom_model": "",
        "google_api_key": "",
        "google_model": "gemini-1.5-pro",
        "google_safety_setting": "medium",
        "local_base_url": "http://localhost:11434/v1",
        "local_model": "",
        "local_model_options": [],
        "openrouter_api_key": "",
        "openrouter_model": "openai/gpt-4o-mini",
        "openrouter_custom_model": "",
        "nvidia_api_key": "",
        "nvidia_nim_base_url": NVIDIA_NIM_BASE_URL,
        "nvidia_model": "meta/llama-3.1-70b-instruct",
        "groq_api_key": "",
        "groq_model": "llama-3.3-70b-versatile",
        "groq_custom_model": "",
        "anthropic_api_key": "",
        "anthropic_model": "claude-sonnet-4-6",
        "anthropic_custom_model": "",
    }


def _settings_from_env() -> dict:
    settings = _default_settings()
    provider = os.getenv("LLM_PROVIDER", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    google_api_key = (
        os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()
    embedding_model = os.getenv("EMBEDDING_MODEL", "").strip()
    google_model = os.getenv("GOOGLE_MODEL", "").strip()
    local_base_url = os.getenv("LOCAL_LLM_BASE_URL", "").strip()
    local_model = os.getenv("LOCAL_LLM_MODEL", "").strip()

    if not provider:
        if openai_api_key == "local-dummy-key" or local_base_url:
            provider = "local"
        elif google_api_key or "generativelanguage.googleapis.com" in base_url:
            provider = "google"
        elif "openrouter.ai" in base_url:
            provider = "openrouter"
        else:
            provider = "openai"

    settings["provider"] = provider
    if provider == "openai":
        settings["openai_api_key"] = ""
        normalized = normalize_model_for_provider("openai", model)
        if normalized:
            if model in STANDARD_OPENAI_MODELS:
                settings["openai_model"] = normalized
            else:
                if normalized in STANDARD_OPENAI_MODELS:
                    settings["openai_model"] = normalized
                else:
                    settings["openai_model"] = "custom"
                    settings["openai_custom_model"] = normalized
        if embedding_model:
            settings["local_embedding_model"] = embedding_model
    elif provider == "google":
        settings["google_api_key"] = ""
        settings["google_model"] = google_model or model or settings["google_model"]
        settings["google_safety_setting"] = os.getenv("GOOGLE_SAFETY_SETTING", "medium")
    elif provider == "openrouter":
        settings["openrouter_api_key"] = ""
        settings["openrouter_model"] = normalize_model_for_provider(
            "openrouter",
            model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        )
        if settings["openrouter_model"] not in [
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-chat",
        ]:
            settings["openrouter_custom_model"] = settings["openrouter_model"]
            settings["openrouter_model"] = "custom"
    elif provider == "nvidia":
        settings["nvidia_api_key"] = ""
        settings["nvidia_nim_base_url"] = os.getenv("NVIDIA_NIM_BASE_URL", NVIDIA_NIM_BASE_URL)
        settings["nvidia_model"] = os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")
    elif provider == "groq":
        settings["groq_api_key"] = ""
        settings["groq_model"] = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        settings["groq_custom_model"] = ""
    elif provider == "anthropic":
        settings["anthropic_api_key"] = ""
        settings["anthropic_model"] = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        settings["anthropic_custom_model"] = ""
    else:
        chosen_local_url = local_base_url or base_url
        chosen_local_model = local_model or model
        settings["local_base_url"] = chosen_local_url or settings["local_base_url"]
        settings["local_model"] = chosen_local_model
        settings["local_model_options"] = (
            [{"label": chosen_local_model, "value": chosen_local_model}]
            if chosen_local_model
            else []
        )
    return settings


def _merge_store_settings(store_data: dict | None) -> dict:
    settings = _settings_from_env()
    if not isinstance(store_data, dict):
        return settings
    merged = settings.copy()
    secret_keys = {"openai_api_key", "google_api_key", "openrouter_api_key"}
    merged.update({k: v for k, v in store_data.items() if v is not None and k not in secret_keys})
    return merged


def callbacks(app):
    # Load from localStorage first, fallback to env.
    @app.callback(
        [
            Output("llm-provider-selector", "value"),
            Output("openai-api-key-input", "value"),
            Output("openai-model-selector", "value"),
            Output("openai-custom-model-input", "value"),
            Output("google-api-key-input", "value"),
            Output("google-model-selector", "value"),
            Output("google-safety-setting", "value"),
            Output("llm-base-url-input", "value"),
            Output("llm-model-input", "value"),
            Output("llm-model-input", "options"),
            Output("openrouter-api-key-input", "value"),
            Output("openrouter-model-selector", "value"),
            Output("openrouter-custom-model-input", "value"),
            Output("nvidia-api-key-input", "value"),
            Output("nvidia-nim-base-url-input", "value"),
            Output("nvidia-model-selector", "value"),
            Output("groq-api-key-input", "value"),
            Output("groq-model-selector", "value"),
            Output("groq-custom-model-input", "value"),
            Output("anthropic-api-key-input", "value"),
            Output("anthropic-model-selector", "value"),
            Output("anthropic-custom-model-input", "value"),
        ],
        Input("main-container", "id"),
        State("llm-settings-store", "data"),
    )
    def load_llm_configuration(_, store_data):
        try:
            settings = _merge_store_settings(store_data)
            return (
                settings["provider"],
                settings["openai_api_key"],
                settings["openai_model"],
                settings["openai_custom_model"],
                settings["google_api_key"],
                settings["google_model"],
                settings["google_safety_setting"],
                settings["local_base_url"],
                settings["local_model"],
                settings["local_model_options"],
                settings["openrouter_api_key"],
                settings["openrouter_model"],
                settings["openrouter_custom_model"],
                settings["nvidia_api_key"],
                settings["nvidia_nim_base_url"],
                settings["nvidia_model"],
                settings["groq_api_key"],
                settings["groq_model"],
                settings["groq_custom_model"],
                settings["anthropic_api_key"],
                settings["anthropic_model"],
                settings["anthropic_custom_model"],
            )
        except Exception as e:
            logger.error(f"Error loading LLM configuration: {e}")
            return (dash.no_update,) * 22

    @app.callback(
        Output("llm-settings-store", "data"),
        [
            Input("llm-provider-selector", "value"),
            Input("openai-api-key-input", "value"),
            Input("openai-model-selector", "value"),
            Input("openai-custom-model-input", "value"),
            Input("google-api-key-input", "value"),
            Input("google-model-selector", "value"),
            Input("google-safety-setting", "value"),
            Input("llm-base-url-input", "value"),
            Input("llm-model-input", "value"),
            Input("llm-model-input", "options"),
            Input("openrouter-api-key-input", "value"),
            Input("openrouter-model-selector", "value"),
            Input("openrouter-custom-model-input", "value"),
            Input("nvidia-api-key-input", "value"),
            Input("nvidia-nim-base-url-input", "value"),
            Input("nvidia-model-selector", "value"),
            Input("groq-api-key-input", "value"),
            Input("groq-model-selector", "value"),
            Input("groq-custom-model-input", "value"),
            Input("anthropic-api-key-input", "value"),
            Input("anthropic-model-selector", "value"),
            Input("anthropic-custom-model-input", "value"),
        ],
    )
    def persist_llm_settings(
        provider,
        _openai_api_key,
        openai_model,
        openai_custom_model,
        _google_api_key,
        google_model,
        google_safety_setting,
        local_base_url,
        local_model,
        local_model_options,
        _openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
        _nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        _groq_api_key,
        groq_model,
        groq_custom_model,
        _anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
    ):
        return {
            "provider": provider,
            "openai_api_key": "",
            "openai_model": openai_model or "gpt-4o-mini",
            "openai_custom_model": openai_custom_model or "",
            "google_api_key": "",
            "google_model": google_model or "gemini-1.5-pro",
            "google_safety_setting": google_safety_setting or "medium",
            "local_base_url": local_base_url or "http://localhost:11434/v1",
            "local_model": local_model or "",
            "local_model_options": local_model_options or [],
            "openrouter_api_key": "",
            "openrouter_model": openrouter_model or "openai/gpt-4o-mini",
            "openrouter_custom_model": openrouter_custom_model or "",
            "nvidia_api_key": "",
            "nvidia_nim_base_url": nvidia_nim_base_url or NVIDIA_NIM_BASE_URL,
            "nvidia_model": nvidia_model or "meta/llama-3.1-70b-instruct",
            "groq_api_key": "",
            "groq_model": groq_model or "llama-3.3-70b-versatile",
            "groq_custom_model": groq_custom_model or "",
            "anthropic_api_key": "",
            "anthropic_model": anthropic_model or "claude-sonnet-4-6",
            "anthropic_custom_model": anthropic_custom_model or "",
        }

    # Toggle provider-specific sections.
    @app.callback(
        [
            Output("openai-config", "style"),
            Output("google-config", "style"),
            Output("openrouter-config", "style"),
            Output("nvidia-config", "style"),
            Output("groq-config", "style"),
            Output("anthropic-config", "style"),
            Output("local-llm-config", "style"),
            Output("google-params-config", "style"),
        ],
        Input("llm-provider-selector", "value"),
    )
    def toggle_llm_config(provider):
        none = {"display": "none"}
        block = {"display": "block"}
        if provider == "openai":
            return block, none, none, none, none, none, none, none
        if provider == "google":
            return none, block, none, none, none, none, none, block
        if provider == "openrouter":
            return none, none, block, none, none, none, none, none
        if provider == "nvidia":
            return none, none, none, block, none, none, none, none
        if provider == "groq":
            return none, none, none, none, block, none, none, none
        if provider == "anthropic":
            return none, none, none, none, none, block, none, none
        # local
        return none, none, none, none, none, none, block, none

    @app.callback(
        Output("openai-custom-model-div", "style"),
        Input("openai-model-selector", "value"),
    )
    def toggle_custom_model_input(selected_model):
        if selected_model == "custom":
            return {"display": "block", "marginTop": "10px"}
        return {"display": "none"}

    @app.callback(
        Output("openrouter-custom-model-div", "style"),
        Input("openrouter-model-selector", "value"),
    )
    def toggle_openrouter_custom_model_input(selected_model):
        if selected_model == "custom":
            return {"display": "block", "marginTop": "10px"}
        return {"display": "none"}

    @app.callback(
        Output("groq-custom-model-div", "style"),
        Input("groq-model-selector", "value"),
    )
    def toggle_groq_custom_model_input(selected_model):
        if selected_model == "custom":
            return {"display": "block", "marginTop": "10px"}
        return {"display": "none"}

    @app.callback(
        Output("anthropic-custom-model-div", "style"),
        Input("anthropic-model-selector", "value"),
    )
    def toggle_anthropic_custom_model_input(selected_model):
        if selected_model == "custom":
            return {"display": "block", "marginTop": "10px"}
        return {"display": "none"}

    @app.callback(
        [
            Output("llm-config-status", "children"),
            Output("llm-status-light", "className"),
            Output("llm-status-light", "title"),
        ],
        Input("verify-llm-connection-btn", "n_clicks"),
        [
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
            State("google-safety-setting", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
            State("openrouter-api-key-input", "value"),
            State("openrouter-model-selector", "value"),
            State("openrouter-custom-model-input", "value"),
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
            State("groq-custom-model-input", "value"),
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
            State("anthropic-custom-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def verify_llm_connection(
        n_clicks,
        provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        local_base_url,
        local_model,
        openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
        nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        groq_api_key,
        groq_model,
        groq_custom_model,
        anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
    ):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        try:
            if provider == "openai":
                openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "").strip()
                if not openai_api_key or not openai_api_key.startswith("sk-"):
                    return (
                        "⚠️ OpenAI API key is not configured",
                        "status-indicator status-warning",
                        "Enter a key for this session or set OPENAI_API_KEY on the server",
                    )
                model = (
                    openai_custom_model.strip()
                    if openai_model == "custom" and openai_custom_model
                    else openai_model
                )
                llm_client.initialize_client(
                    provider="openai",
                    api_key=openai_api_key,
                    model=model,
                    base_url=OPENAI_BASE_URL,
                )
            elif provider == "google":
                google_api_key = (
                    google_api_key
                    or os.getenv("GEMINI_API_KEY", "").strip()
                    or os.getenv("GOOGLE_API_KEY", "").strip()
                )
                if not google_api_key:
                    return (
                        "⚠️ Gemini API key is required",
                        "status-indicator status-warning",
                        "Enter a key for this session or set GEMINI_API_KEY on the server",
                    )
                models = llm_client.get_gemini_models(google_api_key)
                if not models:
                    return (
                        "❌ Google connection failed: no models returned",
                        "status-indicator status-offline",
                        "Gemini models API returned empty result",
                    )
                selected_model = google_model or "gemini-1.5-pro"
                matched = any(
                    m == selected_model or m.startswith(f"{selected_model}-") for m in models
                )
                if not matched:
                    return (
                        f"❌ Google connection failed: model '{selected_model}' not found",
                        "status-indicator status-offline",
                        "Select a model from fetched Gemini model list",
                    )
                llm_client.initialize_client(
                    provider="google",
                    api_key=google_api_key,
                    model=selected_model,
                    base_url=GEMINI_OPENAI_BASE_URL,
                    safety_setting=google_safety_setting or "medium",
                )
                return (
                    f"✅ Google connection verified ({selected_model})",
                    "status-indicator status-online",
                    f"Fetched {len(models)} Gemini models",
                )
            elif provider == "openrouter":
                openrouter_api_key = (
                    openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
                )
                if not openrouter_api_key:
                    return (
                        "⚠️ OpenRouter API key is required",
                        "status-indicator status-warning",
                        "Enter a key for this session or set OPENROUTER_API_KEY on the server",
                    )
                model = (
                    openrouter_custom_model.strip()
                    if openrouter_model == "custom" and openrouter_custom_model
                    else openrouter_model
                )
                llm_client.initialize_client(
                    provider="openrouter",
                    api_key=openrouter_api_key,
                    model=model,
                    base_url=OPENROUTER_BASE_URL,
                )
            elif provider == "nvidia":
                nvidia_api_key = nvidia_api_key or os.getenv("NVIDIA_API_KEY", "").strip()
                if not nvidia_api_key:
                    return (
                        "⚠️ NVIDIA API key is required",
                        "status-indicator status-warning",
                        "Enter a key or set NVIDIA_API_KEY on the server",
                    )
                nim_base_url = (nvidia_nim_base_url or NVIDIA_NIM_BASE_URL).rstrip("/")
                llm_client.initialize_client(
                    provider="nvidia",
                    api_key=nvidia_api_key,
                    base_url=nim_base_url,
                    model=nvidia_model or "meta/llama-3.1-70b-instruct",
                )
            elif provider == "groq":
                groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
                if not groq_api_key:
                    return (
                        "⚠️ Groq API key is required",
                        "status-indicator status-warning",
                        "Enter a key for this session or set GROQ_API_KEY on the server",
                    )
                model = (
                    groq_custom_model.strip()
                    if groq_model == "custom" and groq_custom_model
                    else groq_model
                )
                llm_client.initialize_client(
                    provider="groq",
                    api_key=groq_api_key,
                    model=model,
                    base_url=GROQ_BASE_URL,
                )
            elif provider == "anthropic":
                anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
                if not anthropic_api_key:
                    return (
                        "⚠️ Anthropic API key is required",
                        "status-indicator status-warning",
                        "Enter a key for this session or set ANTHROPIC_API_KEY on the server",
                    )
                model = (
                    anthropic_custom_model.strip()
                    if anthropic_model == "custom" and anthropic_custom_model
                    else anthropic_model
                ) or "claude-sonnet-4-6"
                llm_client.initialize_client(
                    provider="anthropic",
                    api_key=anthropic_api_key,
                    model=model,
                    base_url=ANTHROPIC_BASE_URL,
                )
            else:
                if not local_base_url or not local_model:
                    return (
                        "⚠️ Incomplete Ollama configuration",
                        "status-indicator status-warning",
                        "Provide both base URL and model",
                    )
                resolved_local_url = _normalize_local_base_url(local_base_url)
                llm_client.initialize_client(
                    provider="local",
                    api_key="local-dummy-key",
                    base_url=resolved_local_url,
                    model=local_model,
                )

            success, msg = llm_client.test_connection()
            if success:
                return (
                    f"✅ {provider.title()} connection verified ({llm_client.model})",
                    "status-indicator status-online",
                    msg,
                )
            return (
                f"❌ {provider.title()} connection failed: {_sanitize_error_message(msg)}",
                "status-indicator status-offline",
                _sanitize_error_message(msg),
            )
        except Exception as e:
            logger.error(f"LLM verification error: {e}")
            msg = _sanitize_error_message(str(e))
            return (
                f"❌ Error: {msg}",
                "status-indicator status-offline",
                msg,
            )

    @app.callback(
        Output("active-llm-banner", "children"),
        [
            Input("llm-settings-store", "data"),
            Input("llm-config-status", "children"),
            Input("llm-save-status", "children"),
        ],
        prevent_initial_call=False,
    )
    def show_active_llm_banner(_store, _verify_status, _save_status):
        if llm_client.client or llm_client.anthropic_client:
            return dbc.Alert(
                [
                    html.Span("🟢 ", style={"fontSize": "0.9rem"}),
                    html.Strong("Active: "),
                    html.Span(f"{llm_client.provider.title()} / {llm_client.model}"),
                    html.Br(),
                    html.Small("Loaded from server environment", className="text-muted"),
                ],
                color="success",
                className="py-2 px-3 mb-0",
                style={"fontSize": "0.85rem"},
            )
        return dbc.Alert(
            [
                html.Span("⚪ ", style={"fontSize": "0.9rem"}),
                html.Strong("No LLM configured"),
                html.Br(),
                html.Small("Configure below or set in .env", className="text-muted"),
            ],
            color="secondary",
            className="py-2 px-3 mb-0",
            style={"fontSize": "0.85rem"},
        )

    @app.callback(
        Output("ai-search-toggle", "value"),
        Output("edge-method", "value"),
        Input("llm-settings-store", "data"),
        prevent_initial_call=False,
    )
    def sync_ai_toggle_from_server(_store):
        """Enable AI Search on page load when the server LLM client is already configured."""
        if llm_client.client or llm_client.anthropic_client:
            return True, "semantic"
        return no_update, no_update

    @app.callback(
        Output("normalization-toggle", "value"),
        [
            Input("llm-settings-store", "data"),
            Input("llm-config-status", "children"),
        ],
        prevent_initial_call=False,
    )
    def sync_normalization_toggle(_store, verify_status):
        """Enable KG Normalization only when an LLM client is available.

        Fires on page load (via llm-settings-store) and after each LLM
        verification attempt (via llm-config-status), so the toggle
        accurately reflects whether normalization can actually run.
        """
        if llm_client.client or llm_client.anthropic_client:
            return ["enabled"]
        if isinstance(verify_status, str) and verify_status.startswith("✅"):
            return ["enabled"]
        return []

    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="sync_llm_toggles"),
        [
            Output("ai-search-toggle", "value", allow_duplicate=True),
            Output("edge-method", "value", allow_duplicate=True),
        ],
        [
            Input("llm-provider-selector", "value"),
            Input("openai-api-key-input", "value"),
            Input("google-api-key-input", "value"),
            Input("google-model-selector", "value"),
            Input("llm-base-url-input", "value"),
            Input("llm-model-input", "value"),
            Input("openrouter-api-key-input", "value"),
            Input("openrouter-model-selector", "value"),
            Input("groq-api-key-input", "value"),
            Input("groq-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )

    @app.callback(
        [
            Output("llm-model-input", "options", allow_duplicate=True),
            Output("local-model-fetch-status", "children"),
        ],
        Input("refresh-local-models-btn", "n_clicks"),
        State("llm-base-url-input", "value"),
        prevent_initial_call=True,
    )
    def fetch_local_models(n_clicks, base_url):
        if not n_clicks or not base_url:
            raise dash.exceptions.PreventUpdate
        try:
            base = (base_url or "").strip().rstrip("/")
            if not base:
                return no_update, "⚠️ Enter Local base URL first"

            # Try OpenAI-compatible endpoints first, then native Ollama tags endpoint.
            candidates = [
                f"{base}/models",
                f"{base}/v1/models",
                f"{base}/api/tags",
            ]

            for url in candidates:
                try:
                    response = requests.get(url, timeout=5)
                except Exception:
                    continue
                if response.status_code != 200:
                    continue
                payload = response.json() if response.content else {}
                if url.endswith("/api/tags"):
                    models_list = payload.get("models", [])
                    options = [
                        {"label": m.get("name", "unknown"), "value": m.get("name", "unknown")}
                        for m in models_list
                    ]
                else:
                    models_list = payload.get("data", [])
                    options = [
                        {"label": m.get("id", "unknown"), "value": m.get("id", "unknown")}
                        for m in models_list
                    ]
                options = [o for o in options if o["value"] and o["value"] != "unknown"]
                if options:
                    return options, f"✅ Found {len(options)} models"

            return (
                no_update,
                "❌ Could not fetch models. Try URL like http://<host>:11434 or .../v1",
            )
        except Exception as e:
            logger.error(f"Error fetching local models: {e}")
            return no_update, "❌ Error: Could not connect"

    @app.callback(
        [
            Output("openrouter-model-selector", "options", allow_duplicate=True),
            Output("openrouter-model-fetch-status", "children", allow_duplicate=True),
            Output("openrouter-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-openrouter-models-btn", "n_clicks"),
        [
            State("openrouter-api-key-input", "value"),
            State("openrouter-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_openrouter_models(n_clicks, api_key, current_value):
        api_key = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        if not n_clicks or not api_key:
            return no_update, "⚠️ Enter OpenRouter API key first", no_update
        try:
            models = llm_client.get_openrouter_models(api_key)
            if not models:
                return no_update, "❌ No models found", no_update
            new_options = [{"label": m, "value": m} for m in models]
            new_options.append({"label": "Custom Model...", "value": "custom"})
            new_value = current_value
            if current_value not in models and current_value != "custom":
                new_value = "openai/gpt-4o-mini" if "openai/gpt-4o-mini" in models else models[0]
            return new_options, f"✅ Found {len(models)} models", new_value
        except Exception as e:
            logger.error(f"Error fetching OpenRouter models: {e}")
            return no_update, f"❌ Fetch failed: {_sanitize_error_message(str(e))}", no_update

    @app.callback(
        [
            Output("nvidia-model-selector", "options", allow_duplicate=True),
            Output("nvidia-model-fetch-status", "children"),
            Output("nvidia-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-nvidia-models-btn", "n_clicks"),
        [
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_nvidia_models(n_clicks, api_key, base_url, current_value):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        api_key = api_key or os.getenv("NVIDIA_API_KEY", "").strip()
        nim_url = (base_url or NVIDIA_NIM_BASE_URL).rstrip("/")
        if not api_key:
            return no_update, "⚠️ Enter NVIDIA API key first", no_update
        try:
            resp = requests.get(
                f"{nim_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if resp.status_code != 200:
                return no_update, f"❌ HTTP {resp.status_code}: {resp.text[:120]}", no_update
            data = resp.json().get("data", [])
            options = [{"label": m["id"], "value": m["id"]} for m in data if m.get("id")]
            if not options:
                return no_update, "❌ No models returned", no_update
            new_value = (
                current_value
                if any(o["value"] == current_value for o in options)
                else options[0]["value"]
            )
            return options, f"✅ Found {len(options)} models", new_value
        except Exception as e:
            logger.error(f"Error fetching NVIDIA NIM models: {e}")
            return no_update, f"❌ {_sanitize_error_message(str(e))}", no_update

    def _build_openai_model_options(api_key, current_options, current_value, auto=False):
        api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return no_update, "⚠️ Enter API key first", no_update
        models = llm_client.get_openai_models(api_key)
        if not models:
            return no_update, "❌ No chat models found", no_update

        friendly_names = {
            "gpt-4o": "GPT-4o (Recommended)",
            "gpt-4o-mini": "GPT-4o Mini (Fast & Cheap)",
            "gpt-4.1": "GPT-4.1",
            "gpt-4.1-mini": "GPT-4.1 Mini",
            "o4-mini": "o4-mini (Reasoning)",
            "o3-mini": "o3-mini (Reasoning)",
            "gpt-4-turbo": "GPT-4 Turbo",
            "o1-preview": "o1-preview (Advanced Reasoning)",
            "o1-mini": "o1-mini",
            "gpt-3.5-turbo": "GPT-3.5 Turbo (Legacy)",
        }
        new_options = [{"label": friendly_names.get(m, m), "value": m} for m in models]
        has_custom = any(opt.get("value") == "custom" for opt in (current_options or []))
        if has_custom or True:
            new_options.append({"label": "Custom Model...", "value": "custom"})

        new_value = current_value
        if current_value not in models and current_value != "custom":
            new_value = "gpt-4o-mini" if "gpt-4o-mini" in models else models[0]

        status = f"✅ {'Auto-synced' if auto else 'Found'} {len(models)} models"
        return new_options, status, new_value

    def _build_google_model_options(api_key, current_value, auto=False):
        api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        if not api_key:
            return no_update, "⚠️ Enter Gemini API key first", no_update
        if not api_key.startswith("AIza"):
            return (
                no_update,
                "⚠️ Invalid Gemini API key format (expected prefix 'AIza')",
                no_update,
            )

        models = llm_client.get_gemini_models(api_key)
        if not models:
            return no_update, "❌ No Gemini models found", no_update

        new_options = [{"label": m, "value": m} for m in models]
        new_value = current_value
        if current_value not in models:
            new_value = models[0]
        status = f"✅ {'Auto-synced' if auto else 'Found'} {len(models)} Gemini models"
        return new_options, status, new_value

    @app.callback(
        [
            Output("openai-model-selector", "options", allow_duplicate=True),
            Output("openai-model-fetch-status", "children", allow_duplicate=True),
            Output("openai-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-openai-models-btn", "n_clicks"),
        [
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "options"),
            State("openai-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_openai_models(n_clicks, api_key, current_options, current_value):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        try:
            return _build_openai_model_options(api_key, current_options, current_value, auto=False)
        except Exception as e:
            logger.error(f"Error fetching OpenAI models: {e}")
            return no_update, f"❌ Fetch failed: {_sanitize_error_message(str(e))}", no_update

    @app.callback(
        [
            Output("openai-model-selector", "options", allow_duplicate=True),
            Output("openai-model-fetch-status", "children", allow_duplicate=True),
            Output("openai-model-selector", "value", allow_duplicate=True),
        ],
        [
            Input("llm-provider-selector", "value"),
            Input("openai-api-key-input", "value"),
        ],
        [
            State("openai-model-selector", "options"),
            State("openai-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def auto_fetch_openai_models(provider, api_key, current_options, current_value):
        if provider != "openai":
            raise dash.exceptions.PreventUpdate
        api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or not api_key.startswith("sk-"):
            raise dash.exceptions.PreventUpdate
        try:
            return _build_openai_model_options(api_key, current_options, current_value, auto=True)
        except Exception as e:
            logger.error(f"Error auto-fetching OpenAI models: {e}")
            return no_update, f"❌ Auto-sync failed: {_sanitize_error_message(str(e))}", no_update

    @app.callback(
        [
            Output("google-model-selector", "options", allow_duplicate=True),
            Output("google-model-fetch-status", "children", allow_duplicate=True),
            Output("google-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-google-models-btn", "n_clicks"),
        [
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_google_models(n_clicks, api_key, current_value):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        try:
            return _build_google_model_options(api_key, current_value, auto=False)
        except Exception as e:
            logger.error(f"Error fetching Gemini models: {e}")
            return no_update, f"❌ Fetch failed: {_sanitize_error_message(str(e))}", no_update

    @app.callback(
        [
            Output("google-model-selector", "options", allow_duplicate=True),
            Output("google-model-fetch-status", "children", allow_duplicate=True),
            Output("google-model-selector", "value", allow_duplicate=True),
        ],
        [
            Input("llm-provider-selector", "value"),
            Input("google-api-key-input", "value"),
        ],
        State("google-model-selector", "value"),
        prevent_initial_call=True,
    )
    def auto_fetch_google_models(provider, api_key, current_value):
        if provider != "google":
            raise dash.exceptions.PreventUpdate
        api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        if not api_key:
            raise dash.exceptions.PreventUpdate
        try:
            return _build_google_model_options(api_key, current_value, auto=True)
        except Exception as e:
            logger.error(f"Error auto-fetching Gemini models: {e}")
            return no_update, f"❌ Auto-sync failed: {_sanitize_error_message(str(e))}", no_update

    @app.callback(
        Output("llm-save-status", "children"),
        Input("save-llm-config-btn", "n_clicks"),
        [
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
            State("google-safety-setting", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
            State("openrouter-api-key-input", "value"),
            State("openrouter-model-selector", "value"),
            State("openrouter-custom-model-input", "value"),
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
            State("groq-custom-model-input", "value"),
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
            State("anthropic-custom-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def save_llm_configuration(
        n_clicks,
        provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        local_base_url,
        local_model,
        openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
        nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        groq_api_key,
        groq_model,
        groq_custom_model,
        anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
    ):
        if not n_clicks:
            return ""
        if os.getenv("NETMEDEX_ALLOW_WEB_ENV_WRITE", "false").lower() not in {
            "1",
            "true",
            "yes",
        }:
            return (
                "⚠️ Saving server .env from the web UI is disabled. "
                "Use the current session fields or set NETMEDEX_ALLOW_WEB_ENV_WRITE=true for trusted local use."
            )
        try:
            env_path = Path(__file__).resolve().parents[2] / ".env"
            env_vars = {}
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key.strip()] = value.strip()

            env_vars["LLM_PROVIDER"] = provider
            if provider == "openai":
                if not openai_api_key or not openai_api_key.startswith("sk-"):
                    return "⚠️ Please enter a valid OpenAI API key before saving"
                model = (
                    openai_custom_model.strip()
                    if openai_model == "custom" and openai_custom_model
                    else (openai_model or "gpt-4o-mini")
                )
                model = normalize_model_for_provider("openai", model)
                env_vars["OPENAI_API_KEY"] = openai_api_key
                env_vars["OPENAI_BASE_URL"] = OPENAI_BASE_URL
                env_vars["OPENAI_MODEL"] = model
                env_vars["EMBEDDING_MODEL"] = "text-embedding-3-small"
            elif provider == "google":
                if not google_api_key:
                    return "⚠️ Please enter Gemini API key before saving"
                # Keep provider-specific keys separate.
                env_vars["GEMINI_API_KEY"] = google_api_key
                env_vars["OPENAI_BASE_URL"] = GEMINI_OPENAI_BASE_URL
                env_vars["GOOGLE_MODEL"] = google_model or "gemini-1.5-pro"
                env_vars["OPENAI_MODEL"] = google_model or "gemini-1.5-pro"
                env_vars["EMBEDDING_MODEL"] = "text-embedding-004"
                env_vars["GOOGLE_SAFETY_SETTING"] = google_safety_setting or "medium"
            elif provider == "openrouter":
                if not openrouter_api_key:
                    return "⚠️ Please enter OpenRouter API key before saving"
                model = (
                    openrouter_custom_model.strip()
                    if openrouter_model == "custom" and openrouter_custom_model
                    else (openrouter_model or "openai/gpt-4o-mini")
                )
                model = normalize_model_for_provider("openrouter", model)
                env_vars["OPENROUTER_API_KEY"] = openrouter_api_key
                env_vars["OPENROUTER_MODEL"] = model
                env_vars["OPENAI_BASE_URL"] = OPENROUTER_BASE_URL
                env_vars["OPENAI_MODEL"] = model
                env_vars["EMBEDDING_MODEL"] = "text-embedding-3-small"
            elif provider == "nvidia":
                nvidia_api_key = nvidia_api_key or os.getenv("NVIDIA_API_KEY", "").strip()
                if not nvidia_api_key:
                    return "⚠️ Please enter NVIDIA API key before saving"
                nim_base_url = (nvidia_nim_base_url or NVIDIA_NIM_BASE_URL).rstrip("/")
                nim_model = nvidia_model or "meta/llama-3.1-70b-instruct"
                env_vars["NVIDIA_API_KEY"] = nvidia_api_key
                env_vars["NVIDIA_NIM_BASE_URL"] = nim_base_url
                env_vars["NVIDIA_NIM_MODEL"] = nim_model
                env_vars["OPENAI_BASE_URL"] = nim_base_url
                env_vars["OPENAI_MODEL"] = nim_model
                env_vars["EMBEDDING_MODEL"] = "NV-Embed-QA"
            elif provider == "groq":
                groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
                if not groq_api_key:
                    return "⚠️ Please enter a Groq API key before saving"
                model = (
                    groq_custom_model.strip()
                    if groq_model == "custom" and groq_custom_model
                    else (groq_model or "llama-3.3-70b-versatile")
                )
                env_vars["GROQ_API_KEY"] = groq_api_key
                env_vars["GROQ_MODEL"] = model
                env_vars["OPENAI_BASE_URL"] = GROQ_BASE_URL
                env_vars["OPENAI_MODEL"] = model
                env_vars["EMBEDDING_MODEL"] = "text-embedding-3-small"
            elif provider == "anthropic":
                anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
                if not anthropic_api_key:
                    return "⚠️ Please enter an Anthropic API key before saving"
                model = (
                    anthropic_custom_model.strip()
                    if anthropic_model == "custom" and anthropic_custom_model
                    else (anthropic_model or "claude-sonnet-4-6")
                )
                env_vars["ANTHROPIC_API_KEY"] = anthropic_api_key
                env_vars["ANTHROPIC_MODEL"] = model
                env_vars["OPENAI_MODEL"] = model
            else:
                if not local_base_url or not local_model:
                    return "⚠️ Please enter both base URL and model name before saving"
                resolved_local_url = _normalize_local_base_url(local_base_url)
                env_vars["LOCAL_LLM_API_KEY"] = "local-dummy-key"
                env_vars["LOCAL_LLM_BASE_URL"] = resolved_local_url
                env_vars["LOCAL_LLM_MODEL"] = local_model
                env_vars["OPENAI_API_KEY"] = "local-dummy-key"
                env_vars["OPENAI_BASE_URL"] = resolved_local_url
                env_vars["OPENAI_MODEL"] = local_model
                env_vars["EMBEDDING_MODEL"] = "nomic-embed-text"

            _LLM_KEYS = {
                "LLM_PROVIDER",
                "OPENAI_API_KEY",
                "OPENROUTER_API_KEY",
                "GEMINI_API_KEY",
                "GROQ_API_KEY",
                "NVIDIA_API_KEY",
                "NVIDIA_NIM_BASE_URL",
                "NVIDIA_NIM_MODEL",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_MODEL",
                "OPENAI_BASE_URL",
                "OPENAI_MODEL",
                "OPENROUTER_MODEL",
                "GOOGLE_MODEL",
                "EMBEDDING_MODEL",
                "GOOGLE_SAFETY_SETTING",
                "LOCAL_LLM_API_KEY",
                "LOCAL_LLM_BASE_URL",
                "LOCAL_LLM_MODEL",
                "GROQ_MODEL",
            }
            with open(env_path, "w") as f:
                f.write("# NetMedEx LLM Configuration\n")
                for key in [
                    "LLM_PROVIDER",
                    "OPENAI_API_KEY",
                    "OPENROUTER_API_KEY",
                    "GEMINI_API_KEY",
                    "GROQ_API_KEY",
                    "GROQ_MODEL",
                    "ANTHROPIC_API_KEY",
                    "ANTHROPIC_MODEL",
                    "NVIDIA_API_KEY",
                    "OPENAI_BASE_URL",
                    "OPENAI_MODEL",
                    "OPENROUTER_MODEL",
                    "GOOGLE_MODEL",
                    "EMBEDDING_MODEL",
                    "GOOGLE_SAFETY_SETTING",
                    "LOCAL_LLM_API_KEY",
                    "LOCAL_LLM_BASE_URL",
                    "LOCAL_LLM_MODEL",
                    "NVIDIA_NIM_BASE_URL",
                    "NVIDIA_NIM_MODEL",
                ]:
                    if key in env_vars:
                        f.write(f"{key}={env_vars[key]}\n")
                other_vars = {k: v for k, v in env_vars.items() if k not in _LLM_KEYS}
                if other_vars:
                    f.write("\n# Other Configuration\n")
                    for key, value in other_vars.items():
                        f.write(f"{key}={value}\n")

            from webapp.llm import initialize_llm_client_from_settings

            initialize_llm_client_from_settings(
                llm_client,
                provider=provider,
                openai_api_key=openai_api_key,
                openai_model=openai_model,
                openai_custom_model=openai_custom_model,
                google_api_key=google_api_key,
                google_model=google_model,
                google_safety_setting=google_safety_setting,
                local_base_url=local_base_url,
                local_model=local_model,
                openrouter_api_key=openrouter_api_key,
                openrouter_model=openrouter_model,
                openrouter_custom_model=openrouter_custom_model,
                nvidia_api_key=nvidia_api_key,
                nvidia_nim_base_url=nvidia_nim_base_url,
                nvidia_model=nvidia_model,
                groq_api_key=groq_api_key,
                groq_model=groq_model,
                groq_custom_model=groq_custom_model,
                anthropic_api_key=anthropic_api_key,
                anthropic_model=anthropic_model,
                anthropic_custom_model=anthropic_custom_model,
            )

            return f"✅ LLM settings saved to {env_path.name} ({provider})"
        except Exception as e:
            logger.error(f"Failed to save LLM configuration: {e}")
            return f"❌ Failed to save settings: {str(e)}"

    @app.callback(
        [
            Output("groq-model-selector", "options", allow_duplicate=True),
            Output("groq-model-fetch-status", "children", allow_duplicate=True),
            Output("groq-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-groq-models-btn", "n_clicks"),
        [
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_groq_models(n_clicks, api_key, current_value):
        api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        if not n_clicks or not api_key:
            return dash.no_update, "⚠️ Enter Groq API key first", dash.no_update
        try:
            models = llm_client.get_groq_models(api_key)
            if not models:
                return dash.no_update, "❌ No models found", dash.no_update
            new_options = [{"label": m, "value": m} for m in models]
            if not any(m == current_value for m in models):
                current_value = models[0] if models else dash.no_update
            return new_options, f"✅ Found {len(models)} models", current_value
        except Exception as e:
            logger.error(f"Error fetching Groq models: {e}")
            return dash.no_update, "❌ Error: Could not connect", dash.no_update

    @app.callback(
        [
            Output("anthropic-model-selector", "options", allow_duplicate=True),
            Output("anthropic-model-fetch-status", "children", allow_duplicate=True),
            Output("anthropic-model-selector", "value", allow_duplicate=True),
        ],
        Input("refresh-anthropic-models-btn", "n_clicks"),
        [
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def fetch_anthropic_models(n_clicks, api_key, current_value):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        try:
            models = llm_client.get_anthropic_models(api_key)
            if not models:
                return dash.no_update, "❌ No models found", dash.no_update
            new_options = [{"label": m, "value": m} for m in models]
            new_options.append({"label": "Custom Model...", "value": "custom"})
            new_value = current_value if any(m == current_value for m in models) else models[0]
            return new_options, f"✅ Found {len(models)} models", new_value
        except Exception as e:
            logger.error(f"Error fetching Anthropic models: {e}")
            return dash.no_update, f"❌ Error: {_sanitize_error_message(str(e))}", dash.no_update
