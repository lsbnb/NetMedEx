# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import sys
from pathlib import Path

from netmedex.utils import config_logger

logger = logging.getLogger(__name__)


def main():
    args = parse_args(sys.argv[1:])
    args.entry_func(args)


def pubtator_entry(args):
    from netmedex.cli_utils import load_pmids
    from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
    from netmedex.pubtator import PubTatorAPI

    # Logging
    debug = args.debug
    logfile_name = "pubtator-api" if debug else None
    config_logger(debug, logfile_name)

    # Input
    num_inputs = sum(arg is not None for arg in [args.pmids, args.pmid_file, args.query])
    if num_inputs != 1:
        logger.info("Please specify only one of the following: --query, --pmids, --pmid_file")
        sys.exit()

    # Config
    query = None
    pmid_list = None
    if args.query is not None:
        query = args.query
        suffix = query.replace(" ", "_").replace('"', "")
        savepath = args.output if args.output is not None else f"./query_{suffix}.pubtator"
    else:
        if args.pmids is not None:
            pmid_list = load_pmids(args.pmids, load_from="string")
        elif args.pmid_file is not None:
            logger.info(f"Load PMIDs from: {args.pmid_file}")
            pmid_list = load_pmids(args.pmid_file, load_from="file")
        logger.info(f"Found {len(pmid_list)} PMIDs")
        suffix = f"{pmid_list[0]}_total_{len(pmid_list)}" if pmid_list else ""
        savepath = args.output if args.output is not None else f"./pmids_{suffix}.pubtator"

    # Always use "biocjson" format
    request_format = "biocjson"

    # Request articles
    api = PubTatorAPI(
        query=query,
        pmid_list=pmid_list,
        sort=args.sort,
        request_format=request_format,
        max_articles=args.max_articles,
        full_text=args.full_text,
        queue=None,
    )

    try:
        collection = api.run()
        with open(savepath, "w") as f:
            f.write(collection.to_pubtator_str(annotation_use_identifier_name=args.use_mesh))
        logger.info(f"Save PubTator file to {savepath}")
    except (NoArticles, EmptyInput, UnsuccessfulRequest) as e:
        logger.error(str(e))


def network_entry(args):
    from netmedex.graph import PubTatorGraphBuilder, save_graph
    from netmedex.pubtator_parser import PubTatorIO

    # Logging
    debug = args.debug
    logfile_name = "graph" if debug else None
    config_logger(debug, logfile_name)

    # Input
    pubtator_filepath = Path(args.input)
    if not pubtator_filepath.exists():
        logger.error(f"PubTator file not found: {pubtator_filepath}")
        sys.exit()

    # Output
    if args.output is None:
        savepath = pubtator_filepath.with_suffix(f".{args.format}")
    else:
        savepath = Path(args.output)
        savepath.parent.mkdir(parents=True, exist_ok=True)

    # Parse input PubTator file
    collection = PubTatorIO.parse(pubtator_filepath)

    # Graph
    graph_builder = PubTatorGraphBuilder(node_type=args.node_type)
    graph_builder.add_collection(collection)
    G = graph_builder.build(
        pmid_weights=args.pmid_weight,
        weighting_method=args.weighting_method,
        edge_weight_cutoff=args.cut_weight,
        community=args.community,
        max_edges=args.max_edges,
    )

    # Save graph
    save_graph(G, savepath, output_filetype=args.format)


def webapp_entry(args):
    from webapp.app import main

    main()


def parse_args(args):
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers()

    pubtator_subparser = subparser.add_parser(
        "search",
        parents=[get_pubtator_parser()],
        help="Search PubMed articles and obtain annotations",
    )
    pubtator_subparser.set_defaults(entry_func=pubtator_entry)

    network_subparser = subparser.add_parser(
        "network",
        parents=[get_network_parser()],
        help="Build a network from annotations",
    )
    network_subparser.set_defaults(entry_func=network_entry)

    webapp_subparser = subparser.add_parser(
        "run",
        help="Run NetMedEx app",
    )
    webapp_subparser.set_defaults(entry_func=webapp_entry)

    return parser.parse_args(args)


def get_pubtator_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-q",
        "--query",
        default=None,
        help="Query string",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (default: [CURRENT_DIR].pubtator)",
    )
    parser.add_argument(
        "-p",
        "--pmids",
        default=None,
        type=str,
        help="PMIDs for the articles (comma-separated)",
    )
    parser.add_argument(
        "-f",
        "--pmid_file",
        default=None,
        help="Filepath to load PMIDs (one per line)",
    )
    parser.add_argument(
        "-s",
        "--sort",
        default="date",
        choices=["score", "date"],
        help="Sort articles in descending order by (default: date)",
    )
    parser.add_argument(
        "--max_articles",
        type=int,
        default=1000,
        help="Maximal articles to request from the searching result (default: 1000)",
    )
    parser.add_argument(
        "--full_text",
        action="store_true",
        help="Collect full-text annotations if available",
    )
    parser.add_argument(
        "--use_mesh",
        action="store_true",
        help="Use MeSH vocabulary instead of the most commonly used original text in articles",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information",
    )

    return parser


def get_network_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        help="Path to the pubtator file",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (default: [INPUT_DIR].[FORMAT_EXT])",
    )
    parser.add_argument(
        "-w",
        "--cut_weight",
        type=int,
        default=2,
        help="Discard the edges with weight smaller than the specified value (default: 2)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["xgmml", "html", "json", "pickle"],
        default="html",
        help="Output format (default: html)",
    )
    parser.add_argument(
        "--node_type",
        choices=["all", "mesh", "relation"],
        default="all",
        help="Keep specific types of nodes (default: all)",
    )
    parser.add_argument(
        "--weighting_method",
        choices=["freq", "npmi"],
        default="freq",
        help="Weighting method for network edge (default: freq)",
    )
    parser.add_argument(
        "--pmid_weight",
        default=None,
        help="CSV file for the weight of the edge from a PMID (default: 1)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information",
    )
    parser.add_argument(
        "--community",
        action="store_true",
        help="Divide nodes into distinct communities by the Louvain method",
    )
    parser.add_argument(
        "--max_edges",
        type=int,
        default=0,
        help="Maximum number of edges to display (default: 0, no limit)",
    )

    return parser


if __name__ == "__main__":
    main()
