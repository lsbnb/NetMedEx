
from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc
from webapp.llm import llm_client
from netmedex.pubtator import PubTatorAPI
import asyncio

def callbacks(app):
    
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
                 if 'label' in node:
                     entities.append(node['label'])
                 elif 'id' in node:
                     entities.append(node['id'])

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
                pmids = pmids[:20] # Limit for demo
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
            State("llm-analysis-content", "children")
        ],
        prevent_initial_call=True
    )
    def handle_chat(n_clicks, user_input, history, analysis_context):
        if not n_clicks or not user_input:
            return no_update, no_update
            
        if history is None:
            history = []
        elif not isinstance(history, list):
             history = [history] # Should be list of children
        
        # Add User Message
        user_msg = html.Div([html.B("You: "), html.Span(user_input)], style={"marginBottom": "8px"})
        history.append(user_msg)
        
        # Call LLM
        # We need to maintain context. For this simple implementation, we just send context + current query
        # Ideally, we should keep a proper message list in dcc.Store
        prompt = f"Context from previous analysis:\n{analysis_context}\n\nUser Question: {user_input}"
        
        if llm_client.client:
             try:
                response = llm_client.client.chat.completions.create(
                    model=llm_client.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant answering questions about the analyzed biomedical network."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=300
                )
                ai_text = response.choices[0].message.content
             except Exception as e:
                ai_text = f"Error: {e}"
        else:
            ai_text = "LLM Client not initialized."
            
        ai_msg = html.Div([html.B("AI: "), html.Span(ai_text)], style={"marginBottom": "15px", "backgroundColor": "#e6f3ff", "padding": "5px", "borderRadius": "5px"})
        history.append(ai_msg)
        
        return history, ""

    # API Key Update
    @app.callback(
        Output("api-key-status", "children"),
        Input("openai-api-key-input", "value"),
        prevent_initial_call=True
    )
    def update_api_key(api_key):
        if not api_key:
            return ""
        llm_client.update_api_key(api_key)
        return "API Key Updated!"

