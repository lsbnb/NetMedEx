code = """
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
"""

with open("webapp/callbacks/llm_callbacks.py", "a") as f:
    f.write(code)
