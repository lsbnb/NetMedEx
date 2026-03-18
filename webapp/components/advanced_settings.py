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


llm_config = html.Div(
    [
        dcc.Store(id="llm-settings-store", storage_type="local"),
        generate_param_title(
            "LLM Provider",
            "Choose your LLM provider for AI-powered features",
        ),
        dbc.RadioItems(
            id="llm-provider-selector",
            options=[
                {"label": "OpenAI", "value": "openai"},
                {"label": "Google Gemini", "value": "google"},
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
                    placeholder="AIza...",
                    debounce=True,
                ),
                html.Small(
                    "Use an API key from Google AI Studio.",
                    className="text-muted d-block mt-1",
                    style={"fontSize": "0.8rem"},
                ),
            ],
            id="google-config",
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
                html.Span(id="llm-status-light", className="status-indicator status-unknown"),
                html.Span(id="llm-config-status", className="text-success small"),
            ],
            className="d-flex align-items-center mt-2",
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
                html.Div(id="llm-save-status", className="small mt-2"),
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
                        html.H5("Advanced Settings", className="mb-0"),
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
            ],
            id="advanced-settings-collapse",
            className="settings-collapse",
            style=display.none,
        ),
    ],
    id="advanced-settings",
    className="settings-container",
)
