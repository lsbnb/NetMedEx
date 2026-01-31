from __future__ import annotations

from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc
from webapp.llm import llm_client
from netmedex.pubtator import PubTatorAPI
import asyncio
import logging

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
            return provider, "", "gpt-4o-mini", base_url, model
        else:
            provider = "openai"
            # Check if model is in the dropdown, otherwise set to custom
            standard_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o1-mini", "gpt-3.5-turbo"]
            if model in standard_models:
                return provider, api_key, model, "http://localhost:11434/v1", ""
            else:
                # Custom model
                return provider, api_key, "custom", "http://localhost:11434/v1", ""
    
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
            standard_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o1-mini", "gpt-3.5-turbo"]
            if model and model not in standard_models:
                return model
        return ""
    
    # Open/Close Modal
    @app.callback(
        Output("chat-modal", "is_open"),
        [Input("analyze-btn", "n_clicks"), Input("close-chat-modal", "n_clicks")],
        [State("chat-modal", "is_open")],
    )
    def toggle_modal(n1, n2, is_open):
        if n1 or n2:
            return not is_open
        return is_open

    # Perform Analysis
    @app.callback(
        Output("llm-analysis-content", "children"),
        Input("analyze-btn", "n_clicks"),
        [
            State("cy-graph", "selectedEdgeData"),
            State("cy-graph", "selectedNodeData"),
        ],
        prevent_initial_call=True,
    )
    def perform_analysis(n_clicks, selected_edges, selected_nodes):
        if not n_clicks:
            return no_update

        # Collect PMIDs (focus on edges for now as they contain compendium of articles)
        pmid_set = set()

        entities = []

        if selected_nodes:
            for node in selected_nodes:
                if "label" in node:
                    entities.append(node["label"])
                elif "id" in node:
                    entities.append(node["id"])

        if selected_edges:
            for edge in selected_edges:
                # Edges in Cytoscape output usually have 'source', 'target', and data
                # NetMedEx edges probably store PMIDs in 'pmids' or similar field
                # Need to check graph construction. Usually it's 'pmids' list or comma string
                if "pmids" in edge:
                    if isinstance(edge["pmids"], list):
                        pmid_set.update(edge["pmids"])
                    elif isinstance(edge["pmids"], str):
                        pmid_set.update(edge["pmids"].split(","))

        pmids = list(pmid_set)

        if not pmids and not entities:
            return "No data selected. Please select nodes and edges in the graph."

        if not pmids:
            return f"Selected Entities: {', '.join(entities)}\n\n(No direct PMIDs found in selection to analyze abstracts. Try selecting edges.)"

        # Fetch articles
        # This is blocking. For production, should use background callback.
        # Here we use synchronous run for simplicity of prototype.
        try:
            # We use PubTatorAPI to fetch title+abstract
            # We can use 'pmids' argument.
            # Using max_articles limit to avoid overloading
            if len(pmids) > 20:
                pmids = pmids[:20]  # Limit for demo
                warning = f"(Analysis limited to top 20 of {len(pmid_set)} unique PMIDs)\n\n"
            else:
                warning = ""

            # Re-using PubTatorAPI to fetch
            # Since PubTatorAPI is async under the hood but has run() method
            api = PubTatorAPI(pmid_list=pmids, full_text=False)
            collection = api.run()

            abstracts = []
            for article in collection.articles:
                text = f"Title: {article.title}\nAbstract: {article.abstract}"
                abstracts.append(text)

            summary = llm_client.summarize_abstracts(abstracts)

            return f"{warning}{summary}"

        except Exception as e:
            return f"Error analyzing abstracts: {str(e)}"

    # Chat Interaction
    @app.callback(
        [Output("chat-history", "children"), Output("chat-input", "value")],
        Input("chat-send-btn", "n_clicks"),
        [
            State("chat-input", "value"),
            State("chat-history", "children"),
            State("llm-analysis-content", "children"),
        ],
        prevent_initial_call=True,
    )
    def handle_chat(n_clicks, user_input, history, analysis_context):
        if not n_clicks or not user_input:
            return no_update, no_update

        if history is None:
            history = []
        elif not isinstance(history, list):
            history = [history]  # Should be list of children

        # Add User Message
        user_msg = html.Div(
            [html.B("You: "), html.Span(user_input)], style={"marginBottom": "8px"}
        )
        history.append(user_msg)

        # Call LLM
        # We need to maintain context. For this simple implementation, we just send context + current query
        # Ideally, we should keep a proper message list in dcc.Store
        prompt = (
            f"Context from previous analysis:\n{analysis_context}\n\nUser Question: {user_input}"
        )

        if llm_client.client:
            try:
                response = llm_client.client.chat.completions.create(
                    model=llm_client.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant answering questions about the analyzed biomedical network.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=300,
                )
                ai_text = response.choices[0].message.content
            except Exception as e:
                ai_text = f"Error: {e}"
        else:
            ai_text = "LLM Client not initialized."

        ai_msg = html.Div(
            [html.B("AI: "), html.Span(ai_text)],
            style={
                "marginBottom": "15px",
                "backgroundColor": "#e6f3ff",
                "padding": "5px",
                "borderRadius": "5px",
            },
        )
        history.append(ai_msg)

        return history, ""

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
    def update_llm_configuration(provider, api_key, openai_model, custom_model, base_url, local_model):
        """Update LLM client based on selected provider and configuration"""
        try:
            if provider == "openai":
                if api_key and api_key.startswith("sk-"):
                    # Determine which model to use
                    if openai_model == "custom":
                        model = custom_model if custom_model else "gpt-4o-mini"
                    else:
                        model = openai_model if openai_model else "gpt-4o-mini"
                    
                    llm_client.initialize_client(api_key=api_key, model=model)
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
    def save_llm_configuration(n_clicks, provider, api_key, openai_model, custom_model, base_url, local_model):
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
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
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
            with open(env_path, 'w') as f:
                # Write header comment
                f.write("# OpenAI API Configuration\n")
                
                # Write LLM configuration
                for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]:
                    if key in env_vars:
                        f.write(f"{key}={env_vars[key]}\n")
                
                # Write other non-LLM variables
                other_vars = {k: v for k, v in env_vars.items() 
                             if k not in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]}
                
                if other_vars:
                    f.write("\n# Other Configuration\n")
                    for key, value in other_vars.items():
                        f.write(f"{key}={value}\n")
            
            provider_name = "OpenAI" if provider == "openai" else "Local LLM"
            return f"✅ LLM settings saved successfully to .env ({provider_name})"
            
        except Exception as e:
            logger.error(f"Failed to save LLM configuration: {e}")
            return f"❌ Failed to save settings: {str(e)}"
