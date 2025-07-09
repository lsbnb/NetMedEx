from dash import Input, Output, State, dcc

from netmedex.cytoscape_js import save_as_html
from netmedex.cytoscape_xgmml import save_as_xgmml
from webapp.callbacks.graph_utils import rebuild_graph


def callbacks(app):
    @app.callback(
        Output("download-pubtator", "data"),
        Input("download-pubtator-btn", "n_clicks"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def download_pubtator(n_clicks, savepath):
        if savepath is None:
            return

        return dcc.send_file(savepath["pubtator"], filename="output.pubtator")

    @app.callback(
        Output("export-html", "data"),
        Input("export-btn-html", "n_clicks"),
        State("graph-layout", "value"),
        State("node-degree", "value"),
        State("graph-cut-weight", "value"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def export_html(n_clicks, layout, node_degree, weight, savepath):
        if savepath is None:
            return

        G = rebuild_graph(
            node_degree, weight, format="html", with_layout=True, graph_path=savepath["graph"]
        )
        save_as_html(G, savepath["html"], layout=layout)
        return dcc.send_file(savepath["html"], filename="output.html")

    @app.callback(
        Output("export-xgmml", "data"),
        Input("export-btn-xgmml", "n_clicks"),
        State("graph-layout", "value"),
        State("node-degree", "value"),
        State("graph-cut-weight", "value"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def export_xgmml(n_clicks, layout, node_degree, weight, savepath):
        if savepath is None:
            return

        G = rebuild_graph(
            node_degree, weight, format="xgmml", with_layout=True, graph_path=savepath["graph"]
        )
        save_as_xgmml(G, savepath["xgmml"])
        return dcc.send_file(savepath["xgmml"], filename="output.xgmml")

    @app.callback(
        Output("export-edge-csv", "data"),
        Input("export-edge-btn", "n_clicks"),
        State("cy", "tapEdgeData"),
        State("pmid-title-dict", "data"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def export_edge_csv(n_clicks, tap_edge, pmid_title, savepath):
        import csv

        with open(savepath["edge_info"], "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["PMID", "Title"])
            writer.writerows([[pmid, pmid_title[pmid]] for pmid in tap_edge["pmids"]])
        n1, n2 = tap_edge["label"].split(" (interacts with) ")
        filename = f"{n1}_{n2}.csv"
        return dcc.send_file(savepath["edge_info"], filename=filename)
