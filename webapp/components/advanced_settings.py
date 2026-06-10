from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title
from webapp.utils import display

max_articles = html.Div(
    [
        generate_param_title(
            "Max Articles",
            "Set the maximum number of articles retrieved via API",
        ),
        dcc.Slider(
            10,
            3000,
            10,
            value=30,
            marks=None,
            id="max-articles",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ],
    className="param",
)

max_edges = html.Div(
    [
        generate_param_title(
            "Max Edges",
            "Set the maximum number of edges to display in the graph (0: No limit)",
        ),
        dcc.Slider(
            0,
            1000,
            50,
            value=0,
            marks=None,
            id="max-edges",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ],
    className="param",
)

normalization_toggle = html.Div(
    [
        generate_param_title(
            "KG Normalization",
            (
                "sapBERT-based Knowledge Graph Normalization (v1.1)\n\n"
                "Automatically merges semantically equivalent nodes (e.g., case variants, "
                "abbreviations, and synonyms) using biomedical vector embeddings trained on UMLS.\n\n"
                "💡 Reduces graph redundancy by collapsing near-duplicate entities into a single "
                "canonical node, producing a cleaner and more interpretable knowledge graph.\n\n"
                "⚠️ Requires an active LLM connection (used for embedding generation). "
                "May add processing time for large graphs."
            ),
        ),
        dbc.Checklist(
            options=[
                {
                    "label": "🧬 Enable sapBERT KG Normalization",
                    "value": "enabled",
                },
            ],
            id="normalization-toggle",
            value=[],
            switch=True,
            inline=True,
            className="mt-1",
        ),
    ],
    className="param",
)


llm_config = html.Div(
    [
        dcc.Store(id="llm-settings-store", storage_type="local"),
        html.Div(id="active-llm-banner", className="mb-3"),
        generate_param_title(
            "LLM Provider",
            "Choose your LLM provider for AI-powered features",
        ),
        dbc.RadioItems(
            id="llm-provider-selector",
            options=[
                {"label": "OpenAI", "value": "openai"},
                {"label": "Google Gemini", "value": "google"},
                {"label": "OpenRouter", "value": "openrouter"},
                {"label": "NVIDIA NIM", "value": "nvidia"},
                {"label": "Groq", "value": "groq"},
                {"label": "Anthropic Claude", "value": "anthropic"},
                {"label": "Local Ollama", "value": "local"},
            ],
            value="openai",  # Default to OpenAI
            inline=False,
            className="mb-3",
        ),
        html.H6("Connectivity", className="mt-2"),
        # OpenAI Configuration (shown by default)
        html.Div(
            [
                generate_param_title(
                    "OpenAI API Key",
                    "Enter your OpenAI API Key (starts with sk-...)",
                ),
                dbc.Input(
                    id="openai-api-key-input",
                    type="password",
                    placeholder="sk-...",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="openai-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="openai-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                html.Div(style={"height": "15px"}),  # Spacer
                generate_param_title(
                    "Model",
                    (
                        "Select OpenAI model or choose Custom to specify your own.\n"
                        "💡 Recommended: gpt-4o (High Accuracy) or gpt-4o-mini (Fast & Cheap).\n"
                        "⚠️ For Semantic Analysis, use GPT-4o-mini or higher.\n"
                        "Smaller models (nano, micro, etc.) may produce empty or unreliable results, "
                        "leading to very few or no semantic edges being generated."
                    ),
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="openai-model-selector",
                            options=[
                                {"label": "GPT-4o (Recommended)", "value": "gpt-4o"},
                                {"label": "GPT-4o Mini (Fast & Cheap)", "value": "gpt-4o-mini"},
                                {"label": "GPT-4 Turbo", "value": "gpt-4-turbo"},
                                {
                                    "label": "o1-preview (Advanced Reasoning)",
                                    "value": "o1-preview",
                                },
                                {"label": "o1-mini", "value": "o1-mini"},
                                {"label": "GPT-3.5 Turbo (Legacy)", "value": "gpt-3.5-turbo"},
                                {"label": "Custom Model...", "value": "custom"},
                            ],
                            value="gpt-4o-mini",  # Default
                            clearable=False,
                            className="mb-2",
                            style={"flex": "1"},  # Take available space
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-openai-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2 mb-2",
                            title="Fetch models from OpenAI",
                        ),
                    ],
                    className="d-flex align-items-center",
                ),
                html.Div(id="openai-model-fetch-status", className="small text-muted mb-2"),
                # Conditional custom input (shown when "custom" selected)
                html.Div(
                    [
                        dbc.Input(
                            id="openai-custom-model-input",
                            placeholder="e.g., gpt-4o-2024-08-06",
                            debounce=True,
                        ),
                    ],
                    id="openai-custom-model-div",
                    style={"display": "none"},
                ),
            ],
            id="openai-config",
            style={"display": "block"},
        ),
        # Google Gemini Configuration
        html.Div(
            [
                generate_param_title(
                    "Gemini API Key",
                    "Enter your Gemini API key from Google AI Studio",
                ),
                dbc.Input(
                    id="google-api-key-input",
                    type="password",
                    placeholder="AIza... or AQ.A...",
                    debounce=True,
                ),
                html.Small(
                    "Use an API key from Google AI Studio.",
                    className="text-muted d-block mt-1",
                    style={"fontSize": "0.8rem"},
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="google-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="google-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
            ],
            id="google-config",
            style={"display": "none"},
        ),
        # OpenRouter Configuration
        html.Div(
            [
                dbc.Alert(
                    [
                        html.Strong("⚠️ KG Normalization unavailable: "),
                        "OpenRouter does not provide a native embeddings API endpoint. "
                        "The sapBERT KG Normalization feature will be disabled when using OpenRouter.",
                    ],
                    color="warning",
                    className="py-2 px-3 mb-3",
                    style={"fontSize": "0.82rem"},
                ),
                generate_param_title(
                    "OpenRouter API Key",
                    "Enter your OpenRouter API Key (starts with sk-or-...)",
                ),
                dbc.Input(
                    id="openrouter-api-key-input",
                    type="password",
                    placeholder="sk-or-...",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="openrouter-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="openrouter-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                html.Div(style={"height": "15px"}),
                generate_param_title(
                    "Model",
                    "Select or fetch models from OpenRouter (e.g., anthropic/claude-3-opus).",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="openrouter-model-selector",
                            options=[
                                {
                                    "label": "GPT-4o Mini (OpenRouter)",
                                    "value": "openai/gpt-4o-mini",
                                },
                                {
                                    "label": "Claude 3.5 Sonnet",
                                    "value": "anthropic/claude-3.5-sonnet",
                                },
                                {"label": "DeepSeek V3", "value": "deepseek/deepseek-chat"},
                                {"label": "Custom...", "value": "custom"},
                            ],
                            value="openai/gpt-4o-mini",
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-openrouter-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from OpenRouter",
                        ),
                    ],
                    className="d-flex align-items-center mb-2",
                ),
                html.Div(id="openrouter-model-fetch-status", className="small text-muted mb-2"),
                html.Div(
                    [
                        dbc.Input(
                            id="openrouter-custom-model-input",
                            placeholder="e.g., meta-llama/llama-3-70b-instruct",
                            debounce=True,
                        ),
                    ],
                    id="openrouter-custom-model-div",
                    style={"display": "none"},
                ),
            ],
            id="openrouter-config",
            style={"display": "none"},
        ),
        # NVIDIA NIM Configuration (hidden by default)
        html.Div(
            [
                generate_param_title(
                    "NVIDIA API Key",
                    "API key from build.nvidia.com (starts with nvapi-...).\nFor on-premises NIM, use any non-empty value.",
                ),
                dbc.Input(
                    id="nvidia-api-key-input",
                    type="password",
                    placeholder="nvapi-...",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="nvidia-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="nvidia-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                html.Div(style={"height": "10px"}),
                generate_param_title(
                    "Base URL",
                    "Cloud NIM: https://integrate.api.nvidia.com/v1\nOn-premises NIM: http://<host>:<port>/v1",
                ),
                dbc.Input(
                    id="nvidia-nim-base-url-input",
                    placeholder="https://integrate.api.nvidia.com/v1",
                    value="https://integrate.api.nvidia.com/v1",
                    debounce=True,
                ),
                html.Div(style={"height": "10px"}),
                generate_param_title(
                    "Model",
                    "Select a preset NIM model or fetch the full list from your endpoint.",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="nvidia-model-selector",
                            options=[
                                {
                                    "label": "Llama 3.1 70B Instruct",
                                    "value": "meta/llama-3.1-70b-instruct",
                                },
                                {
                                    "label": "Llama 3.1 8B Instruct",
                                    "value": "meta/llama-3.1-8b-instruct",
                                },
                                {
                                    "label": "Llama 3.3 70B Instruct",
                                    "value": "meta/llama-3.3-70b-instruct",
                                },
                                {
                                    "label": "Nemotron 70B Instruct",
                                    "value": "nvidia/llama-3.1-nemotron-70b-instruct",
                                },
                                {
                                    "label": "Mixtral 8x22B Instruct",
                                    "value": "mistralai/mixtral-8x22b-instruct-v0.1",
                                },
                                {
                                    "label": "Mistral Large",
                                    "value": "mistralai/mistral-large-latest",
                                },
                            ],
                            value="meta/llama-3.1-70b-instruct",
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-nvidia-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from NIM endpoint",
                        ),
                    ],
                    className="d-flex align-items-center",
                ),
                html.Div(id="nvidia-model-fetch-status", className="small text-muted mt-1"),
            ],
            id="nvidia-config",
            style={"display": "none"},
        ),
        # Groq Configuration (hidden by default)
        html.Div(
            [
                dbc.Alert(
                    [
                        html.Strong("⚠️ KG Normalization unavailable: "),
                        "Groq does not provide an embeddings API endpoint. "
                        "The sapBERT KG Normalization feature will be disabled when using Groq.",
                    ],
                    color="warning",
                    className="py-2 px-3 mb-3",
                    style={"fontSize": "0.82rem"},
                ),
                generate_param_title(
                    "Groq API Key",
                    "Enter your Groq API Key (starts with gsk_...)",
                ),
                dbc.Input(
                    id="groq-api-key-input",
                    type="password",
                    placeholder="gsk_...",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="groq-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="groq-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                html.Div(style={"height": "10px"}),
                generate_param_title(
                    "Model",
                    "Select a model from Groq.",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="groq-model-selector",
                            options=[
                                {
                                    "label": "Llama 3.3 70B Versatile",
                                    "value": "llama-3.3-70b-versatile",
                                },
                                {"label": "Llama 3.1 8B Instant", "value": "llama-3.1-8b-instant"},
                                {"label": "Mixtral 8x7B", "value": "mixtral-8x7b-32768"},
                                {"label": "Gemma 2 9B", "value": "gemma2-9b-it"},
                                {"label": "Custom...", "value": "custom"},
                            ],
                            value="llama-3.3-70b-versatile",
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-groq-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from Groq",
                        ),
                    ],
                    className="d-flex align-items-center mb-2",
                ),
                html.Div(id="groq-model-fetch-status", className="small text-muted mb-2"),
                html.Div(
                    [
                        dbc.Input(
                            id="groq-custom-model-input",
                            placeholder="e.g., llama-3.3-70b-versatile",
                            debounce=True,
                        ),
                    ],
                    id="groq-custom-model-div",
                    style={"display": "none"},
                ),
            ],
            id="groq-config",
            style={"display": "none"},
        ),
        # Anthropic Claude Configuration (hidden by default)
        html.Div(
            [
                dbc.Alert(
                    [
                        html.Strong("⚠️ KG Normalization unavailable: "),
                        "Anthropic does not provide a native embeddings API. "
                        "The sapBERT KG Normalization feature will be disabled when using Claude.",
                    ],
                    color="warning",
                    className="py-2 px-3 mb-3",
                    style={"fontSize": "0.82rem"},
                ),
                generate_param_title(
                    "Anthropic API Key",
                    "Enter your Anthropic API Key (starts with sk-ant-...)",
                ),
                dbc.Input(
                    id="anthropic-api-key-input",
                    type="password",
                    placeholder="sk-ant-...",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="anthropic-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="anthropic-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                html.Div(style={"height": "10px"}),
                generate_param_title(
                    "Model",
                    "Select a Claude model.\n💡 Recommended: claude-sonnet-4-6 (balanced) or claude-opus-4-8 (most capable).",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="anthropic-model-selector",
                            options=[
                                {
                                    "label": "Claude Opus 4.8 (Most Capable)",
                                    "value": "claude-opus-4-8",
                                },
                                {
                                    "label": "Claude Sonnet 4.6 (Recommended)",
                                    "value": "claude-sonnet-4-6",
                                },
                                {"label": "Claude Haiku 4.5 (Fast)", "value": "claude-haiku-4-5"},
                                {
                                    "label": "Claude 3.7 Sonnet",
                                    "value": "claude-3-7-sonnet-20250219",
                                },
                                {
                                    "label": "Claude 3.5 Sonnet",
                                    "value": "claude-3-5-sonnet-20241022",
                                },
                                {
                                    "label": "Claude 3.5 Haiku",
                                    "value": "claude-3-5-haiku-20241022",
                                },
                                {"label": "Custom...", "value": "custom"},
                            ],
                            value="claude-sonnet-4-6",
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-anthropic-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from Anthropic",
                        ),
                    ],
                    className="d-flex align-items-center mb-2",
                ),
                html.Div(id="anthropic-model-fetch-status", className="small text-muted mb-2"),
                html.Div(
                    [
                        dbc.Input(
                            id="anthropic-custom-model-input",
                            placeholder="e.g., claude-sonnet-4-6",
                            debounce=True,
                        ),
                    ],
                    id="anthropic-custom-model-div",
                    style={"display": "none"},
                ),
            ],
            id="anthropic-config",
            style={"display": "none"},
        ),
        # Local LLM Configuration (hidden by default)
        html.Div(
            [
                generate_param_title(
                    "Base URL",
                    "Local LLM endpoint (OpenAI-compatible API)",
                ),
                dbc.Input(
                    id="llm-base-url-input",
                    placeholder="http://localhost:11434/v1",
                    value="http://localhost:11434/v1",
                    debounce=True,
                ),
                html.Div(
                    [
                        dbc.Button(
                            "Submit",
                            id="local-key-submit-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Reset",
                            id="local-key-reset-btn",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                    ],
                    className="d-flex mt-2",
                ),
                generate_param_title(
                    "Model Name",
                    (
                        "Model to use (e.g., gpt-oss:20b, llama3:8b).\n"
                        "💡 Recommended: Models with 8B+ parameters (e.g., llama3:8b, mistral) for stable extraction."
                    ),
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="llm-model-input",
                            placeholder="Select or fetch models...",
                            options=[],
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-local-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from Local LLM",
                        ),
                    ],
                    className="d-flex align-items-center",
                ),
                html.Div(id="local-model-fetch-status", className="small text-muted mt-1"),
            ],
            id="local-llm-config",
            style={"display": "none"},
        ),
        html.H6("Parameters", className="mt-3"),
        html.Div(
            [
                generate_param_title(
                    "Gemini Model",
                    (
                        "Choose a Gemini model version.\n"
                        "💡 Recommended: gemini-2.0-flash (Fast & Capable) or gemini-1.5-pro (Deep Reasoning)."
                    ),
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="google-model-selector",
                            options=[
                                {
                                    "label": "gemini-2.0-flash (Latest Flash)",
                                    "value": "gemini-2.0-flash",
                                },
                                {"label": "gemini-1.5-pro (Reasoning)", "value": "gemini-1.5-pro"},
                                {"label": "gemini-1.5-flash", "value": "gemini-1.5-flash"},
                            ],
                            value="gemini-2.0-flash",
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        dbc.Button(
                            html.I(className="bi bi-arrow-clockwise"),
                            id="refresh-google-models-btn",
                            color="secondary",
                            outline=True,
                            className="ms-2",
                            title="Fetch models from Gemini",
                        ),
                    ],
                    className="d-flex align-items-center",
                ),
                html.Div(id="google-model-fetch-status", className="small text-muted mt-1"),
                generate_param_title(
                    "Safety Settings",
                    "Gemini content filtering level.",
                ),
                dcc.Dropdown(
                    id="google-safety-setting",
                    options=[
                        {"label": "Unrestricted", "value": "none"},
                        {"label": "Low Filtering", "value": "low"},
                        {"label": "Moderate Filtering", "value": "medium"},
                    ],
                    value="medium",
                    clearable=False,
                ),
            ],
            id="google-params-config",
            style={"display": "none"},
        ),
        html.Div(
            [
                dbc.Button(
                    "Verify Connection",
                    id="verify-llm-connection-btn",
                    color="primary",
                    outline=True,
                    size="sm",
                    className="mt-3",
                ),
            ]
        ),
        # Unified status message and connection light
        html.Div(
            [
                html.Span(
                    id="llm-status-light",
                    className="status-indicator status-offline",
                    style={"marginTop": "0"},
                ),
                html.Span(id="llm-config-status", className="small ms-1"),
            ],
            className="d-flex align-items-center mt-2",
            style={"minHeight": "20px"},
        ),
        # Save LLM Settings button
        html.Div(
            [
                dbc.Button(
                    "💾 Save LLM Settings to .env",
                    id="save-llm-config-btn",
                    color="success",
                    size="sm",
                    className="mt-3 w-100",
                ),
                html.Div(id="llm-save-status", className="small mt-1 text-success"),
            ],
            className="mt-2",
        ),
    ],
    className="param",
)


advanced_settings = html.Div(
    [
        dbc.Button(
            html.Img(src=dash.get_asset_url("icon_config.svg"), width=22, height=22),
            # "Settings",
            id="advanced-settings-btn",
            className="btn-secondary settings",
        ),
        html.Span(
            [
                html.Img(src=dash.get_asset_url("icon_info.svg"), className="info-img"),
            ],
            className="info-outer info-right",
            **{
                "data-tooltip": "Settings for LLM configuration and fetching PubMed literature",
                "data-x": "0px",
                "data-y": "0px",
            },
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H4("Advanced Settings", className="mb-0 fw-semibold"),
                        html.Button(
                            type="button",
                            className="btn-close",
                            id="close-advanced-settings-btn",
                            **{"aria-label": "Close"},
                        ),
                    ],
                    className="d-flex justify-content-between align-items-center mb-2",
                ),
                llm_config,
                max_articles,
                max_edges,
                normalization_toggle,
            ],
            id="advanced-settings-collapse",
            className="settings-collapse",
            style=display.none,
        ),
    ],
    id="advanced-settings",
    className="settings-container",
)
