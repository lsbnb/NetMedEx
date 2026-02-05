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
                html.Div(id="model-fetch-status", className="small text-muted mt-1"),
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
