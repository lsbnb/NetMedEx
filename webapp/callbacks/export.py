from __future__ import annotations

import os

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

        import os

        # Prefer BioC-JSON (preserves journal/date/authors) over plain pubtator format
        biocjson_path = savepath.get("biocjson", "")
        if biocjson_path and os.path.exists(biocjson_path):
            return dcc.send_file(biocjson_path, filename="output.biocjson")

        if not os.path.exists(savepath["pubtator"]):
             return None # Silent failure or add alert if possible

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

        if not os.path.exists(savepath["graph"]):
            return None

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

    @app.callback(
        Output("export-graph", "data"),
        Input("export-btn-graph", "n_clicks"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def export_graph_pickle(n_clicks, savepath):
        """Export the full graph state as a pickle file.

        The exported .pkl file contains the complete NetworkX graph including
        all node/edge attributes, pmid_title, pmid_abstract, and semantic
        analysis results. It can be re-loaded in the Search Panel (Graph File
        source) to restore the session without re-running the pipeline.
        """
        if savepath is None or not savepath.get("graph") or not os.path.exists(savepath["graph"]):
            return None

        return dcc.send_file(savepath["graph"], filename="netmedex_graph.pkl")

    @app.callback(
        Output("export-ris", "data"),
        Input("export-btn-ris", "n_clicks"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def export_ris(n_clicks, savepath):
        """Export bibliography of articles in the graph in RIS format."""
        from netmedex.graph import load_graph
        from netmedex.pubtator_data import PubTatorArticle
        from netmedex.pubtator_parser import PubTatorIO
        from netmedex.ris_exporter import convert_to_ris

        if savepath is None or not savepath.get("graph"):
            return

        G = load_graph(savepath["graph"])
        pmid_metadata = G.graph.get("pmid_metadata", {})
        pmid_title = G.graph.get("pmid_title", {})
        bioc_meta = {}

        # Enrich RIS fields from original BioC-JSON when graph metadata is incomplete.
        biocjson_path = savepath.get("biocjson", "")
        if biocjson_path and os.path.exists(biocjson_path):
            collection = PubTatorIO.parse(biocjson_path)
            for article in collection.articles:
                bioc_meta[str(article.pmid)] = {
                    "journal": article.journal,
                    "date": article.date,
                    "doi": article.doi,
                    "volume": article.volume,
                    "issue": article.issue,
                    "pages": article.pages,
                    "authors": (article.metadata or {}).get("authors"),
                }

        articles = []
        # Use pmid_title to ensure we only export PMIDs that have a title in the graph
        for pmid, title in pmid_title.items():
            meta = pmid_metadata.get(str(pmid), {})
            fallback = bioc_meta.get(str(pmid), {})
            authors = meta.get("authors") or fallback.get("authors")
            citation_count = meta.get("citation_count")
            articles.append(
                PubTatorArticle(
                    pmid=pmid,
                    title=title,
                    journal=meta.get("journal") or fallback.get("journal"),
                    date=meta.get("date") or fallback.get("date"),
                    doi=meta.get("doi") or fallback.get("doi"),
                    volume=meta.get("volume") or fallback.get("volume"),
                    issue=meta.get("issue") or fallback.get("issue"),
                    pages=meta.get("pages") or fallback.get("pages"),
                    abstract=None,
                    annotations=[],
                    relations=[],
                    metadata={
                        "authors": authors,
                        "citation_count": citation_count,
                    },
                )
            )

        if not articles:
            return

        ris_content = convert_to_ris(articles)
        with open(savepath["ris"], "w") as f:
            f.write(ris_content)

        return dcc.send_file(savepath["ris"], filename="citations.ris")
