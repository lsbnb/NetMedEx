from __future__ import annotations

import base64
import threading
from queue import Queue
import logging

from dash import Input, Output, State, no_update

from netmedex.cli_utils import load_pmids
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from netmedex.graph import PubTatorGraphBuilder, save_graph
from netmedex.pubtator import PubTatorAPI
from netmedex.pubtator_parser import PubTatorIO
from netmedex.utils_threading import run_thread_with_error_notification
from webapp.llm import llm_client
from webapp.utils import generate_session_id, get_data_savepath, visibility

logger = logging.getLogger(__name__)


def callbacks(app):
    @app.callback(
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("is-new-graph", "data"),
        Output("pmid-title-dict", "data"),
        Output("current-session-path", "data"),
        Output("total-stats", "data"),
        Input("submit-button", "n_clicks"),
        [
            State("api-toggle-items", "value"),
            State("sort-toggle-methods", "value"),
            State("input-type-selection", "value"),
            State("data-input", "value"),
            State("pmid-file-data", "contents"),
            State("pubtator-file-data", "contents"),
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
    ):
        _exception_msg = None
        _exception_type = None

        def custom_hook(args):
            nonlocal _exception_msg
            nonlocal _exception_type
            _exception_msg = args.exc_value
            _exception_type = args.exc_type

        use_mesh = "use_mesh" in pubtator_params
        full_text = "full_text" in pubtator_params
        community = "community" in cy_params
        savepath = get_data_savepath(generate_session_id())

        query = None
        pmid_list = None
        if source == "api":
            if input_type == "query":
                query = data_input
                if ai_search_toggle:
                    set_progress((0, 1, "", "(Step 0/2) AI Translating query..."))
                    translated_query = llm_client.translate_query_to_boolean(query)
                    if translated_query != query:
                        query = translated_query
                        # Ideally notify user, but we'll just log it via progress for now or implicit via results
                        set_progress((0, 1, "", f"AI Translated: {query}"))
            elif input_type == "pmids":
                pmid_list = load_pmids(data_input, load_from="string")
            elif input_type == "pmid_file":
                content_type, content_string = pmid_file_data.split(",")
                decoded_content = base64.b64decode(content_string).decode("utf-8")
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
                )
                if issubclass(_exception_type, known_exceptions):
                    exception_msg = str(_exception_msg)
                else:
                    exception_msg = "An unexpected error occurred."
                set_progress((1, 1, "", exception_msg))
                return (no_update, weight, False, no_update, no_update, "0", "0", "0")

            job.join()
        elif source == "file":
            with open(savepath["pubtator"], "w") as f:
                content_type, content_string = pubtator_file_data.split(",")
                decoded_content = base64.b64decode(content_string).decode("utf-8")
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
                return (no_update, weight, False, no_update, no_update, "0", "0", "0")

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
                    set_progress(
                        (
                            current,
                            total_articles,
                            f"{current}/{total_articles}",
                            f"❌ Error: {error}",
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
        )

        # Parse collection if not already done
        if collection is None:
            collection = PubTatorIO.parse(savepath["pubtator"])

        graph_builder.add_collection(collection)

        # Show building progress
        if edge_method == "semantic":
            set_progress((1, 1, "", "Building graph structure..."))

        G = graph_builder.build(
            pmid_weights=None,
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

        return (
            visibility.visible,
            weight,
            True,
            G.graph["pmid_title"],
            savepath,
            {"articles": num_articles, "nodes": num_nodes, "edges": num_edges},
        )
