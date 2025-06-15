import base64
import threading
from queue import Queue

from dash import Input, Output, State, no_update

from netmedex.cli_utils import load_pmids
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from netmedex.graph import PubTatorGraphBuilder, save_graph
from netmedex.pubtator import PubTatorAPI
from netmedex.pubtator_parser import PubTatorIO
from netmedex.utils_threading import run_thread_with_error_notification
from webapp.utils import generate_session_id, get_data_savepath, visibility


def callbacks(app):
    @app.long_callback(
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("memory-graph-cut-weight", "data", allow_duplicate=True),
        Output("is-new-graph", "data"),
        Output("pmid-title-dict", "data"),
        Output("current-session-path", "data"),
        Input("submit-button", "n_clicks"),
        [
            State("api-toggle-items", "value"),
            State("sort-toggle-methods", "value"),
            State("input-type-selection", "value"),
            State("data-input", "value"),
            State("pmid-file-data", "contents"),
            State("pubtator-file-data", "contents"),
            State("cut-weight", "value"),
            State("max-edges", "value"),
            State("max-articles", "value"),
            State("pubtator-params", "value"),
            State("cy-params", "value"),
            State("weighting-method", "value"),
            State("node-type", "value"),
        ],
        running=[(Input("submit-button", "disabled"), True, False)],
        progress=[
            Output("progress", "value"),
            Output("progress", "max"),
            Output("progress", "label"),
            Output("progress-status", "children"),
        ],
        prevent_initial_call=True,
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
                return (no_update, weight, False, no_update, no_update)

            job.join()
        elif source == "file":
            with open(savepath["pubtator"], "w") as f:
                content_type, content_string = pubtator_file_data.split(",")
                decoded_content = base64.b64decode(content_string).decode("utf-8")
                f.write(decoded_content)

        set_progress((0, 1, "0/1", "Generating network..."))
        graph_builder = PubTatorGraphBuilder(node_type=node_type)
        collection = PubTatorIO.parse(savepath["pubtator"])
        graph_builder.add_collection(collection)
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

        return (visibility.visible, weight, True, G.graph["pmid_title"], savepath)
