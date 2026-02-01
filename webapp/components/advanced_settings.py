from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title
from webapp.utils import visibility

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
            value=200,
            marks=None,
            id="max-edges",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ],
    className="param",
)


llm_config = html.Div(
    [
        generate_param_title(
            "LLM Provider",
            "Choose your LLM provider for AI-powered features",
        ),
        dbc.RadioItems(
            id="llm-provider-selector",
            options=[
                {"label": "OpenAI", "value": "openai"},
                {"label": "Local LLM (e.g., Ollama)", "value": "local"},
            ],
            value="openai",  # Default to OpenAI
            inline=True,
            className="mb-3",
        ),
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
                    "Select OpenAI model or choose Custom to specify your own",
                ),
                dcc.Dropdown(
                    id="openai-model-selector",
                    options=[
                        {"label": "GPT-4o (Recommended)", "value": "gpt-4o"},
                        {"label": "GPT-4o Mini (Fast & Cheap)", "value": "gpt-4o-mini"},
                        {"label": "GPT-4 Turbo", "value": "gpt-4-turbo"},
                        {"label": "o1-preview (Advanced Reasoning)", "value": "o1-preview"},
                        {"label": "o1-mini", "value": "o1-mini"},
                        {"label": "GPT-3.5 Turbo (Legacy)", "value": "gpt-3.5-turbo"},
                        {"label": "Custom Model...", "value": "custom"},
                    ],
                    value="gpt-4o-mini",  # Default
                    clearable=False,
                    className="mb-2",
                ),
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
                    "Model to use (e.g., gpt-oss:20b, llama2)",
                ),
                dbc.Input(
                    id="llm-model-input",
                    placeholder="gpt-oss:20b",
                    debounce=True,
                ),
            ],
            id="local-llm-config",
            style={"display": "none"},
        ),
        # Unified status message
        html.Div(id="llm-config-status", className="text-success small mt-2"),
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
                html.H5("Advanced Settings", className="text-center"),
                llm_config,
                max_articles,
                max_edges,
            ],
            id="advanced-settings-collapse",
            className="settings-collapse",
            style=visibility.hidden,
        ),
    ],
    id="advanced-settings",
    className="settings-container",
)
