from __future__ import annotations

import dash
from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc
from webapp.llm import llm_client
from netmedex.pubtator import PubTatorAPI
import asyncio
import logging
import requests

logger = logging.getLogger(__name__)


def callbacks(app):
    # Load LLM Configuration from .env on page load
    @app.callback(
        [
            Output("llm-provider-selector", "value"),
            Output("openai-api-key-input", "value"),
            Output("openai-model-selector", "value"),
            Output("llm-base-url-input", "value"),
            Output("llm-model-input", "value"),
            Output("llm-model-input", "options"),
        ],
        Input("sidebar-container", "id"),  # Triggered on page load
    )
    def load_llm_configuration(_):
        """Load LLM configuration from environment variables"""
        import os

        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Determine provider based on base_url or api_key
        if api_key == "local-dummy-key" or (base_url and base_url != "https://api.openai.com/v1"):
            provider = "local"
            # For local, also populate the model input
            # Setup options with the current model
            options = [{"label": model, "value": model}] if model else []
            return provider, "", "gpt-4o-mini", base_url, model, options
        else:
            provider = "openai"
            # Check if model is in the dropdown, otherwise set to custom
            standard_models = [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "o1-preview",
                "o1-mini",
                "gpt-3.5-turbo",
            ]
            if model in standard_models:
                return provider, api_key, model, "http://localhost:11434/v1", "", []
            else:
                # Custom model
                return provider, api_key, "custom", "http://localhost:11434/v1", "", []

    # Populate custom model input when loading from env
    @app.callback(
        Output("openai-custom-model-input", "value"),
        Input("openai-model-selector", "value"),
    )
    def populate_custom_model(selected_model):
        """Populate custom model input when custom is selected during env load"""
        import os

        if selected_model == "custom":
            model = os.getenv("OPENAI_MODEL", "")
            standard_models = [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "o1-preview",
                "o1-mini",
                "gpt-3.5-turbo",
            ]
            if model and model not in standard_models:
                return model
        return ""

    # Toggle LLM Configuration Sections
    @app.callback(
        [Output("openai-config", "style"), Output("local-llm-config", "style")],
        Input("llm-provider-selector", "value"),
    )
    def toggle_llm_config(provider):
        """Show/hide configuration sections based on selected provider"""
        if provider == "openai":
            return {"display": "block"}, {"display": "none"}
        else:  # local
            return {"display": "none"}, {"display": "block"}

    # Toggle Custom Model Input for OpenAI
    @app.callback(
        Output("openai-custom-model-div", "style"),
        Input("openai-model-selector", "value"),
    )
    def toggle_custom_model_input(selected_model):
        """Show custom model input when 'custom' is selected"""
        if selected_model == "custom":
            return {"display": "block", "marginTop": "10px"}
        return {"display": "none"}

    # Unified LLM Configuration
    @app.callback(
        Output("llm-config-status", "children"),
        [
            Input("llm-provider-selector", "value"),
            Input("openai-api-key-input", "value"),
            Input("openai-model-selector", "value"),
            Input("openai-custom-model-input", "value"),
            Input("llm-base-url-input", "value"),
            Input("llm-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def update_llm_configuration(
        provider, api_key, openai_model, custom_model, base_url, local_model
    ):
        """Update LLM client based on selected provider and configuration"""
        try:
            if provider == "openai":
                if api_key and api_key.startswith("sk-"):
                    # Determine which model to use
                    if openai_model == "custom":
                        model = custom_model if custom_model else "gpt-4o-mini"
                    else:
                        model = openai_model if openai_model else "gpt-4o-mini"

                    llm_client.initialize_client(
                        api_key=api_key,
                        model=model,
                        base_url="https://api.openai.com/v1",
                    )
                    return f"✅ OpenAI configured with {model}"
                elif api_key:
                    return "⚠️ Invalid API key format (should start with sk-)"
                else:
                    return ""

            else:  # local
                if base_url and local_model:
                    llm_client.initialize_client(
                        api_key="local-dummy-key",  # Dummy key for local LLM
                        base_url=base_url,
                        model=local_model,
                    )
                    return f"✅ Local LLM configured: {local_model}"
                elif base_url or local_model:
                    return "⚠️ Please provide both base URL and model name"
                else:
                    return ""

        except Exception as e:
            return f"❌ Configuration error: {str(e)}"

    # Fetch Local Models
    @app.callback(
        [
            Output("llm-model-input", "options", allow_duplicate=True),
            Output("model-fetch-status", "children"),
        ],
        Input("refresh-local-models-btn", "n_clicks"),
        State("llm-base-url-input", "value"),
        prevent_initial_call=True,
    )
    def fetch_local_models(n_clicks, base_url):
        """Fetch available models from the local LLM endpoint"""
        if not n_clicks or not base_url:
            raise dash.exceptions.PreventUpdate

        try:
            # Construct the models endpoint URL
            # OpenAI compatible endpoint is usually /v1/models
            if base_url.endswith("/"):
                url = f"{base_url}models"
            else:
                url = f"{base_url}/models"

            logger.info(f"Fetching models from {url}")
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                models_list = data.get("data", [])

                # Format for dropdown
                options = []
                for model in models_list:
                    model_id = model.get("id", "unknown")
                    options.append({"label": model_id, "value": model_id})

                count = len(options)
                return options, f"✅ Found {count} models"
            else:
                return no_update, f"❌ Check URL (Status: {response.status_code})"

        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return no_update, f"❌ Error: Could not connect to {base_url}"

    # Fetch OpenAI Models
    @app.callback(
        [
            Output("openai-model-selector", "options", allow_duplicate=True),
            Output("openai-model-fetch-status", "children"),
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
        """Fetch available models from OpenAI API"""
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        if not api_key:
            return no_update, "⚠️ Enter API Key first", no_update

        try:
            logger.info("Fetching OpenAI models using provided key")
            models = llm_client.get_openai_models(api_key)

            if not models:
                return no_update, "❌ No chat models found", no_update

            # Create new options
            new_options = [{"label": m, "value": m} for m in models]

            # Preserve "Custom Model..." option if it existed
            has_custom = False
            for opt in current_options:
                if opt["value"] == "custom":
                    has_custom = True
                    break

            if has_custom:
                new_options.append({"label": "Custom Model...", "value": "custom"})
            else:
                # Add it anyway as it's useful
                new_options.append({"label": "Custom Model...", "value": "custom"})

            # Check if current value is still valid
            new_value = current_value
            if current_value not in models and current_value != "custom":
                # If current model not returned, default to first or keep custom
                if "gpt-4o-mini" in models:
                    new_value = "gpt-4o-mini"
                elif models:
                    new_value = models[0]

            return new_options, f"✅ Found {len(models)} models", new_value

        except Exception as e:
            logger.error(f"Error fetching OpenAI models: {e}")
            return no_update, f"❌ Fetch failed: {str(e)}", no_update

    # Save LLM Configuration to .env file
    @app.callback(
        Output("llm-save-status", "children"),
        Input("save-llm-config-btn", "n_clicks"),
        [
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def save_llm_configuration(
        n_clicks, provider, api_key, openai_model, custom_model, base_url, local_model
    ):
        """Save LLM configuration to .env file"""
        if not n_clicks:
            return ""

        try:
            import os
            from pathlib import Path

            # Get the .env file path (should be in project root)
            env_path = Path(__file__).parent.parent / ".env"

            # Read existing .env file
            env_vars = {}
            if env_path.exists():
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key.strip()] = value.strip()

            # Update LLM-related variables based on provider
            if provider == "openai":
                if not api_key or not api_key.startswith("sk-"):
                    return "⚠️ Please enter a valid OpenAI API key before saving"

                # Determine which model to save
                if openai_model == "custom":
                    model = custom_model if custom_model else "gpt-4o-mini"
                else:
                    model = openai_model if openai_model else "gpt-4o-mini"

                env_vars["OPENAI_API_KEY"] = api_key
                env_vars["OPENAI_MODEL"] = model
                env_vars["OPENAI_BASE_URL"] = "https://api.openai.com/v1"

            else:  # local
                if not base_url or not local_model:
                    return "⚠️ Please enter both base URL and model name before saving"

                env_vars["OPENAI_API_KEY"] = "local-dummy-key"
                env_vars["OPENAI_MODEL"] = local_model
                env_vars["OPENAI_BASE_URL"] = base_url

            # Write back to .env file
            with open(env_path, "w") as f:
                # Write header comment
                f.write("# OpenAI API Configuration\n")

                # Write LLM configuration
                for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]:
                    if key in env_vars:
                        f.write(f"{key}={env_vars[key]}\n")

                # Write other non-LLM variables
                other_vars = {
                    k: v
                    for k, v in env_vars.items()
                    if k not in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]
                }

                if other_vars:
                    f.write("\n# Other Configuration\n")
                    for key, value in other_vars.items():
                        f.write(f"{key}={value}\n")

            provider_name = "OpenAI" if provider == "openai" else "Local LLM"
            return f"✅ LLM settings saved successfully to .env ({provider_name})"

        except Exception as e:
            logger.error(f"Failed to save LLM configuration: {e}")
            return f"❌ Failed to save settings: {str(e)}"
