from __future__ import annotations

import base64
import logging
import pickle
import threading
from queue import Queue

import networkx as nx
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, no_update

from netmedex.cli_utils import load_pmids
from netmedex.exceptions import EmptyInput, NoArticles, RetryableError, UnsuccessfulRequest
from netmedex.graph import PubTatorGraphBuilder, save_graph
from netmedex.pubtator import PubTatorAPI
from netmedex.pubtator_parser import PubTatorIO
from netmedex.utils_threading import run_thread_with_error_notification
from webapp.llm import GEMINI_OPENAI_BASE_URL, OPENAI_BASE_URL
from webapp.llm import llm_client
from webapp.utils import generate_session_id, get_data_savepath, visibility

logger = logging.getLogger(__name__)


def detect_query_language(text: str) -> str:
    """
    Detect the primary language of a query string using Unicode character ranges.
    Returns a human-readable language name suitable for use in LLM prompts.
    """
    if not text:
        return "English"
    # Japanese: Hiragana (U+3040-U+309F) or Katakana (U+30A0-U+30FF)
    if any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" for c in text):
        return "Japanese"
    # Korean: Hangul (U+AC00-U+D7AF)
    if any("\uac00" <= c <= "\ud7af" for c in text):
        return "Korean"
    # CJK Unified Ideographs — Chinese (after Japanese check, so this catches Chinese)
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "Traditional Chinese"
    return "English"


def callbacks(app):
    @app.callback(
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("is-new-graph", "data"),
        Output("pmid-title-dict", "data"),
        Output("current-session-path", "data"),
        Output("total-stats", "data"),
        Output("session-language", "data"),
        Output("output", "children", allow_duplicate=True),
        Input("submit-button", "n_clicks"),
        [
            State("api-toggle-items", "value"),
            State("sort-toggle-methods", "value"),
            State("input-type-selection", "value"),
            State("data-input", "value"),
            State("pmid-file-data", "contents"),
            State("pubtator-file-data", "contents"),
            State("graph-file-data", "contents"),
            State("graph-cut-weight", "value"),
            State("max-edges", "value"),
            State("max-articles", "value"),
            State("pubtator-params", "value"),
            State("cy-params", "value"),
            State("weighting-method", "value"),
            State("node-type", "value"),
            State("ai-search-toggle", "value"),
            State("edge-method", "value"),
            State("semantic-threshold", "value"),
            # LLM Configuration States (to handle background process isolation)
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
            State("google-safety-setting", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
        ],
        running=[
            (Output("submit-button", "disabled"), True, False),
        ],
        progress=[
            Output("progress", "value"),
            Output("progress", "max"),
            Output("progress", "label"),
            Output("progress-status", "children"),
        ],
        prevent_initial_call=True,
        background=True,
        cancel=[Input("reset-button", "n_clicks")],
    )
    def run_pubtator3_api(
        set_progress,
        btn,
        source,
        sort_by,
        input_type,
        data_input,
        pmid_file_data,
        pubtator_file_data,
        graph_file_data,
        weight,
        max_edges,
        max_articles,
        pubtator_params,
        cy_params,
        weighting_method,
        node_type,
        ai_search_toggle,
        edge_method,
        semantic_threshold,
        llm_provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        llm_base_url,
        llm_model,
    ):
        try:
            # Initialize LLM Client for the background process
            if llm_provider == "openai":
                model = openai_custom_model if openai_model == "custom" else openai_model
                llm_client.initialize_client(
                    api_key=openai_api_key,
                    model=model,
                    base_url=OPENAI_BASE_URL,
                    provider="openai",
                )
            elif llm_provider == "google":
                llm_client.initialize_client(
                    api_key=google_api_key,
                    model=google_model,
                    base_url=GEMINI_OPENAI_BASE_URL,
                    provider="google",
                    safety_setting=google_safety_setting,
                )
            else:  # local
                llm_client.initialize_client(
                    api_key="local-dummy-key",
                    base_url=llm_base_url,
                    model=llm_model,
                    provider="local",
                )
            logger.info(
                f"LLM Client initialized in background process: provider={llm_provider}, model={llm_client.model}"
            )

            _exception_msg = None
            _exception_type = None

            def custom_hook(args):
                nonlocal _exception_msg
                nonlocal _exception_type
                _exception_msg = args.exc_value
                _exception_type = args.exc_type

            use_mesh = "use_mesh" in pubtator_params
            full_text = "full_text" in pubtator_params
            fetch_citations = "fetch_citations" in pubtator_params
            community = "community" in cy_params
            savepath = get_data_savepath(generate_session_id())

            # ----------------------------------------------------------------
            # GRAPH FILE BYPASS: restore session from uploaded .pkl file
            # ----------------------------------------------------------------
            if source == "graph_file":
                if not graph_file_data:
                    raise EmptyInput("No Graph file uploaded")

                content_type, content_string = graph_file_data.split(",")
                graph_bytes = base64.b64decode(content_string)

                # Write pickle to session path
                with open(savepath["graph"], "wb") as f:
                    f.write(graph_bytes)

                # Load and validate
                with open(savepath["graph"], "rb") as f:
                    G = pickle.load(f)

                if not isinstance(G, nx.Graph):
                    raise ValueError(
                        "Invalid Graph file: not a NetworkX Graph object. "
                        "Please upload a file exported from NetMedEx Graph Panel."
                    )
                required_keys = ["pmid_title"]
                for k in required_keys:
                    if k not in G.graph:
                        raise ValueError(
                            f"Invalid Graph file: missing required metadata '{k}'. "
                            "Please upload a file exported from NetMedEx Graph Panel."
                        )

                num_articles = len(G.graph.get("pmid_title", {}))
                num_nodes = G.number_of_nodes()
                num_edges = G.number_of_edges()
                set_progress((1, 1, "1/1", "Graph restored from file!"))
                logger.info(
                    f"Graph file loaded: {num_articles} articles, "
                    f"{num_nodes} nodes, {num_edges} edges"
                )
                return (
                    visibility.visible,
                    weight,
                    True,
                    G.graph["pmid_title"],
                    savepath,
                    {"articles": num_articles, "nodes": num_nodes, "edges": num_edges},
                    "English",  # Default language; user can switch in Chat
                    "",  # Clear any previous error
                )
            # ----------------------------------------------------------------

            def decode_file_content(content_string):
                decoded_bytes = base64.b64decode(content_string)
                try:
                    return decoded_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    return decoded_bytes.decode("latin-1")

            # Detect language from the raw user query (before AI translation)
            detected_language = (
                detect_query_language(data_input)
                if input_type == "query" and data_input
                else "English"
            )
            logger.info(f"Detected query language: {detected_language}")

            if source == "api":
                query = None
                pmid_list = None
                # ... (existing api logic mostly unchanged, but we need to update the pmid_file decoding too)
                if input_type == "query":
                    query = data_input

                    if ai_search_toggle:
                        if not llm_client.client:
                            set_progress(
                                (
                                    0,
                                    1,
                                    "",
                                    "⚠️ AI Search skipped: LLM not configured. Using original query.",
                                )
                            )
                        else:
                            set_progress((0, 1, "", "(Step 0/2) AI Translating query..."))
                            try:
                                translated_query = llm_client.translate_query_to_boolean(query)
                                if translated_query and translated_query.strip():
                                    query = translated_query.strip()
                                    set_progress((0, 1, "", f"AI Translated: {query}"))
                                else:
                                    logger.warning(
                                        "AI Search returned empty result, falling back to original query"
                                    )
                                    set_progress(
                                        (
                                            0,
                                            1,
                                            "",
                                            "⚠️ AI Search returned empty. Using original query.",
                                        )
                                    )
                            except Exception as e:
                                logger.error(f"Error executing AI search: {e}")
                                # Continue with original query instead of failing
                                set_progress(
                                    (
                                        0,
                                        1,
                                        "",
                                        f"AI Translation Failed: {e}. Using original query.",
                                    )
                                )
                    else:
                        # Mandatory English translation for non-English queries when AI search is off
                        detected_lang = detect_query_language(query)
                        if detected_lang != "English" and llm_client.client:
                            set_progress(
                                (0, 1, "", f"Translating {detected_lang} query to English...")
                            )
                            try:
                                translated_query = llm_client.translate_to_english(query)
                                if translated_query != query:
                                    query = translated_query
                                    set_progress((0, 1, "", f"Translated to English: {query}"))
                            except Exception as e:
                                logger.error(f"Error executing translation: {e}")
                                set_progress(
                                    (
                                        0,
                                        1,
                                        "",
                                        f"Translation Failed: {e}. Using original query.",
                                    )
                                )

                elif input_type == "pmids":
                    pmid_list = load_pmids(data_input, load_from="string")
                elif input_type == "pmid_file":
                    if not pmid_file_data:
                        raise EmptyInput("No PMID file uploaded")
                    content_type, content_string = pmid_file_data.split(",")
                    decoded_content = decode_file_content(content_string)
                    decoded_content = decoded_content.replace("\n", ",")
                    pmid_list = load_pmids(decoded_content, load_from="string")

                queue = Queue()
                threading.excepthook = custom_hook

                def run_pubtator_and_save():
                    result = PubTatorAPI(
                        query=query,
                        pmid_list=pmid_list,
                        sort=sort_by,
                        max_articles=max_articles,
                        full_text=full_text,
                        queue=queue,
                    ).run()
                    with open(savepath["pubtator"], "w") as f:
                        f.write(result.to_pubtator_str(annotation_use_identifier_name=use_mesh))

                job = threading.Thread(
                    target=run_thread_with_error_notification(run_pubtator_and_save, queue),
                )
                set_progress((0, 1, "", "(Step 1/2) Finding articles..."))

                job.start()
                while True:
                    progress = queue.get()
                    if progress is None:
                        break
                    status, n, total = progress.split("/")
                    if status.startswith("search"):
                        status_msg = "(Step 1/2) Finding articles..."
                    elif status == "get":
                        status_msg = "(Step 2/2) Retrieving articles..."
                    else:
                        status_msg = ""
                    progress_bar_msg = f"{n}/{total}"
                    set_progress((int(n), int(total), progress_bar_msg, status_msg))

                if _exception_type is not None:
                    known_exceptions = (
                        EmptyInput,
                        NoArticles,
                        UnsuccessfulRequest,
                        RetryableError,
                    )
                    if issubclass(_exception_type, known_exceptions):
                        if issubclass(_exception_type, NoArticles) and query:
                            logger.info(f"No articles found for query: {query}")
                        exception_msg = str(_exception_msg)
                    else:
                        logger.error(
                            f"Unexpected error in pipeline: {_exception_msg}", exc_info=True
                        )
                        exception_msg = f"An unexpected error occurred: {str(_exception_msg)}"
                    set_progress((1, 1, "", exception_msg))
                    return (
                        no_update,
                        weight,
                        False,
                        no_update,
                        no_update,
                        {"articles": 0, "nodes": 0, "edges": 0},
                        no_update,  # keep existing session-language
                        html.Div(
                            dbc.Alert(exception_msg, color="danger", dismissable=True),
                            className="mt-3",
                        ),
                    )

                job.join()
            elif source == "file":
                if not pubtator_file_data:
                    raise EmptyInput("No PubTator file uploaded")
                with open(savepath["pubtator"], "w") as f:
                    content_type, content_string = pubtator_file_data.split(",")
                    decoded_content = decode_file_content(content_string)
                    f.write(decoded_content)

            set_progress((0, 1, "0/1", "Generating network..."))

            # Initialize LLM client if using semantic edge method
            llm_for_graph = None
            # Check LLM configuration for semantic analysis
            if edge_method == "semantic":
                if not llm_client.client:
                    set_progress(
                        (
                            1,
                            1,
                            "",
                            "Error: Semantic analysis requires LLM configuration. Please set your API key in Advanced Settings.",
                        )
                    )
                    return (
                        no_update,
                        weight,
                        False,
                        no_update,
                        no_update,
                        {"articles": 0, "nodes": 0, "edges": 0},
                        no_update,
                        html.Div(
                            dbc.Alert(
                                "Error: Semantic analysis requires LLM configuration. Please set your API key in Advanced Settings.",
                                color="danger",
                                dismissable=True,
                            ),
                            className="mt-3",
                        ),
                    )

            # Semantic Analysis: Parse collection first to get article count
            llm_for_graph = llm_client if edge_method == "semantic" else None

            if edge_method == "semantic":
                # Parse early to show accurate progress
                collection = PubTatorIO.parse(savepath["pubtator"])
                total_articles = len(collection.articles)

                # Define progress callback for semantic analysis
                def progress_callback(current, total, status, error):
                    """Callback to update progress during semantic analysis"""
                    logger.info(
                        f"Progress callback: current={current}, total={total}, status={status}, error={error}"
                    )
                    if error:
                        short_error = str(error).split("\n", 1)[0]
                        set_progress(
                            (
                                current,
                                total_articles,
                                f"{current}/{total_articles}",
                                f"⚠️ Skipped one article: {short_error} (continuing)",
                            )
                        )
                    else:
                        set_progress(
                            (
                                current,
                                total_articles,
                                f"{current}/{total_articles}",
                                f"🤖 Semantic Analysis: {status}",
                            )
                        )

                set_progress(
                    (
                        0,
                        total_articles,
                        f"0/{total_articles}",
                        f"Starting semantic analysis for {total_articles} articles (this may take 2-3 seconds per article)...",
                    )
                )
            else:
                # For non-semantic methods, parse later
                collection = None
                progress_callback = None

            graph_builder = PubTatorGraphBuilder(
                node_type=node_type,
                edge_method=edge_method,
                llm_client=llm_for_graph,
                semantic_threshold=semantic_threshold,
                progress_callback=progress_callback,
                fetch_citations=fetch_citations,
            )

            # Parse collection if not already done
            if collection is None:
                collection = PubTatorIO.parse(savepath["pubtator"])

            graph_builder.add_collection(collection)

            # Show building progress
            if edge_method == "semantic":
                set_progress((1, 1, "", "Building graph structure..."))

            # Calculate and apply citation-based weights if fetched
            pmid_weights = None
            if fetch_citations:
                set_progress((1, 1, "", "Calculating citation-normalized weights..."))
                pmid_weights = graph_builder.calculate_citation_weights()

            G = graph_builder.build(
                pmid_weights=pmid_weights,
                weighting_method=weighting_method,
                edge_weight_cutoff=0,
                community=False,
                max_edges=0,
            )

            # Keeping track of the graph's metadata
            G.graph["is_community"] = True if community else False
            G.graph["max_edges"] = max_edges

            save_graph(G, savepath["html"], "html")
            save_graph(G, savepath["graph"], "pickle")

            # Calculate statistics for display
            num_articles = len(G.graph["pmid_title"]) if G.graph.get("pmid_title") else 0
            num_nodes = G.number_of_nodes() if G else 0
            num_edges = G.number_of_edges() if G else 0
            semantic_stats = G.graph.get("semantic_stats", {})
            semantic_failed = int(semantic_stats.get("failed_articles", 0))
            semantic_total = int(semantic_stats.get("total_articles", 0))
            semantic_parse_failures = int(semantic_stats.get("parse_failures", 0))
            semantic_relaxed_recoveries = int(semantic_stats.get("relaxed_recoveries", 0))
            semantic_compact_retries = int(semantic_stats.get("compact_retries", 0))
            semantic_coverage_passes = int(semantic_stats.get("coverage_passes", 0))
            semantic_coverage_expansions = int(semantic_stats.get("coverage_expansions", 0))
            semantic_dropped_threshold = int(semantic_stats.get("dropped_by_threshold", 0))
            semantic_dropped_invalid_nodes = int(semantic_stats.get("dropped_invalid_nodes", 0))
            semantic_provider = (
                getattr(llm_client, "provider", "") if edge_method == "semantic" else ""
            )
            semantic_model = getattr(llm_client, "model", "") if edge_method == "semantic" else ""

            warning_output = ""
            if edge_method == "semantic" and semantic_total > 0 and semantic_failed > 0:
                warning_output = html.Div(
                    dbc.Alert(
                        [
                            html.Div(
                                f"Semantic analysis completed with partial failures: "
                                f"{semantic_failed}/{semantic_total} articles failed due to LLM/API errors. "
                                "Graph was still generated from successful articles."
                            ),
                            html.Hr(),
                            html.Div(
                                (
                                    f"Diagnostics: provider={semantic_provider}, model={semantic_model}, "
                                    f"parse_failures={semantic_parse_failures}, "
                                    f"relaxed_recoveries={semantic_relaxed_recoveries}, "
                                    f"compact_retries={semantic_compact_retries}, "
                                    f"coverage_passes={semantic_coverage_passes}, "
                                    f"coverage_expansions={semantic_coverage_expansions}, "
                                    f"dropped_threshold={semantic_dropped_threshold}, "
                                    f"dropped_invalid_nodes={semantic_dropped_invalid_nodes}"
                                ),
                                className="small mb-0",
                            ),
                        ],
                        color="warning",
                        dismissable=True,
                    ),
                    className="mt-3",
                )
            if edge_method == "semantic" and num_edges == 0:
                warning_output = html.Div(
                    dbc.Alert(
                        [
                            html.Div(
                                "Semantic analysis completed but no semantic edges were generated. "
                                "This usually means most LLM calls failed or confidence filtering removed all relations. "
                                "Try a smaller query, different model, or lower semantic threshold."
                            ),
                            html.Hr(),
                            html.Div(
                                (
                                    f"Diagnostics: provider={semantic_provider}, model={semantic_model}, "
                                    f"parse_failures={semantic_parse_failures}, "
                                    f"relaxed_recoveries={semantic_relaxed_recoveries}, "
                                    f"compact_retries={semantic_compact_retries}, "
                                    f"coverage_passes={semantic_coverage_passes}, "
                                    f"coverage_expansions={semantic_coverage_expansions}, "
                                    f"dropped_threshold={semantic_dropped_threshold}, "
                                    f"dropped_invalid_nodes={semantic_dropped_invalid_nodes}"
                                ),
                                className="small mb-0",
                            ),
                        ],
                        color="warning",
                        dismissable=True,
                    ),
                    className="mt-3",
                )
            elif edge_method == "semantic":
                warning_output = html.Div(
                    dbc.Alert(
                        html.Div(
                            (
                                f"Semantic diagnostics: provider={semantic_provider}, model={semantic_model}, "
                                f"parse_failures={semantic_parse_failures}, "
                                f"relaxed_recoveries={semantic_relaxed_recoveries}, "
                                f"compact_retries={semantic_compact_retries}, "
                                f"coverage_passes={semantic_coverage_passes}, "
                                f"coverage_expansions={semantic_coverage_expansions}, "
                                f"dropped_threshold={semantic_dropped_threshold}, "
                                f"dropped_invalid_nodes={semantic_dropped_invalid_nodes}"
                            ),
                            className="small mb-0",
                        ),
                        color="info",
                        dismissable=True,
                    ),
                    className="mt-3",
                )

            print(f"DEBUG: run_pubtator3_api completed! num_articles={num_articles}")
            return (
                visibility.visible,
                weight,
                True,
                G.graph["pmid_title"],
                savepath,
                {"articles": num_articles, "nodes": num_nodes, "edges": num_edges},
                detected_language,
                warning_output,
            )

        except Exception as e:
            logger.error(f"Unexpected error in run_pubtator3_api: {e}", exc_info=True)
            set_progress((1, 1, "", f"❌ Internal Error: {str(e)}"))
            return (
                no_update,
                weight,
                False,
                no_update,
                no_update,
                {"articles": 0, "nodes": 0, "edges": 0},
                no_update,  # keep existing session-language
                html.Div(
                    dbc.Alert(
                        f"An unexpected error occurred: {str(e)}",
                        color="danger",
                        dismissable=True,
                    ),
                    className="mt-3",
                ),
            )
