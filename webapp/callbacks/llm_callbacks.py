from __future__ import annotations

import logging
import os
from pathlib import Path

import dash
import requests
from dash import ClientsideFunction, Input, Output, State, no_update

from webapp.llm import (
    GEMINI_OPENAI_BASE_URL,
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
    }


def _settings_from_env() -> dict:
    settings = _default_settings()
    provider = os.getenv("LLM_PROVIDER", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    google_api_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
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
    else:
        chosen_local_url = local_base_url or base_url
        chosen_local_model = local_model or model
        settings["local_base_url"] = chosen_local_url or settings["local_base_url"]
        settings["local_model"] = chosen_local_model
        settings["local_model_options"] = (
            [{"label": chosen_local_model, "value": chosen_local_model}] if chosen_local_model else []
        )
    return settings


def _merge_store_settings(store_data: dict | None) -> dict:
    settings = _settings_from_env()
    if not isinstance(store_data, dict):
        return settings
    merged = settings.copy()
    secret_keys = {"openai_api_key", "google_api_key", "openrouter_api_key"}
    merged.update(
        {k: v for k, v in store_data.items() if v is not None and k not in secret_keys}
    )
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
            )
        except Exception as e:
            logger.error(f"Error loading LLM configuration: {e}")
            return (dash.no_update,) * 13

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
        ],
    )
    def persist_llm_settings(
        provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        local_base_url,
        local_model,
        local_model_options,
        openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
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
        }

    # Toggle provider-specific sections.
    @app.callback(
        [
            Output("openai-config", "style"),
            Output("google-config", "style"),
            Output("openrouter-config", "style"),
            Output("local-llm-config", "style"),
            Output("google-params-config", "style"),
        ],
        Input("llm-provider-selector", "value"),
    )
    def toggle_llm_config(provider):
        if provider == "openai":
            return (
                {"display": "block"},
                {"display": "none"},
                {"display": "none"},
                {"display": "none"},
                {"display": "none"},
            )
        if provider == "google":
            return (
                {"display": "none"},
                {"display": "block"},
                {"display": "none"},
                {"display": "none"},
                {"display": "block"},
            )
        if provider == "openrouter":
            return (
                {"display": "none"},
                {"display": "none"},
                {"display": "block"},
                {"display": "none"},
                {"display": "none"},
            )
        return (
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            {"display": "block"},
            {"display": "none"},
        )

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
                matched = any(m == selected_model or m.startswith(f"{selected_model}-") for m in models)
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
                openrouter_api_key = openrouter_api_key or os.getenv(
                    "OPENROUTER_API_KEY", ""
                ).strip()
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

    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="sync_llm_toggles"),
        [
            Output("ai-search-toggle", "value"),
            Output("edge-method", "value"),
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
        ],
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

            return no_update, "❌ Could not fetch models. Try URL like http://<host>:11434 or .../v1"
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
                with open(env_path, "r") as f:
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

            with open(env_path, "w") as f:
                f.write("# NetMedEx LLM Configuration\n")
                for key in [
                    "LLM_PROVIDER",
                    "OPENAI_API_KEY",
                    "OPENROUTER_API_KEY",
                    "GEMINI_API_KEY",
                    "OPENAI_BASE_URL",
                    "OPENAI_MODEL",
                    "OPENROUTER_MODEL",
                    "GOOGLE_MODEL",
                    "EMBEDDING_MODEL",
                    "GOOGLE_SAFETY_SETTING",
                    "LOCAL_LLM_API_KEY",
                    "LOCAL_LLM_BASE_URL",
                    "LOCAL_LLM_MODEL",
                ]:
                    if key in env_vars:
                        f.write(f"{key}={env_vars[key]}\n")
                other_vars = {
                    k: v
                    for k, v in env_vars.items()
                    if k
                    not in {
                        "LLM_PROVIDER",
                        "OPENAI_API_KEY",
                        "OPENROUTER_API_KEY",
                        "GEMINI_API_KEY",
                        "OPENAI_BASE_URL",
                        "OPENAI_MODEL",
                        "OPENROUTER_MODEL",
                        "GOOGLE_MODEL",
                        "EMBEDDING_MODEL",
                        "GOOGLE_SAFETY_SETTING",
                        "LOCAL_LLM_API_KEY",
                        "LOCAL_LLM_BASE_URL",
                        "LOCAL_LLM_MODEL",
                    }
                }
                if other_vars:
                    f.write("\n# Other Configuration\n")
                    for key, value in other_vars.items():
                        f.write(f"{key}={value}\n")

            return f"✅ LLM settings saved to {env_path.name} ({provider})"
        except Exception as e:
            logger.error(f"Failed to save LLM configuration: {e}")
            return f"❌ Failed to save settings: {str(e)}"
