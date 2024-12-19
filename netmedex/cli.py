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
    from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
    from netmedex.pubtator_core import PubTatorAPI
    from netmedex.pubtator_utils import create_savepath, load_pmids

    debug = args.debug
    logfile_name = "search" if debug else None
    config_logger(debug, logfile_name)

    num_inputs = sum(arg is not None for arg in [args.pmids, args.pmid_file, args.query])
    if num_inputs != 1:
        logger.info("Please specify only one of the following: --query, --pmids, --pmid_file")
        sys.exit()

    query = None
    pmid_list = None
    if args.query is not None:
        search_type = "query"
        query = args.query
    elif args.pmids is not None:
        search_type = "pmids"
        pmid_list = load_pmids(args.pmids, load_from="string")
        logger.info(f"Find {len(pmid_list)} PMIDs")
    elif args.pmid_file is not None:
        search_type = "pmids"
        logger.info(f"Load PMIDs from: {args.pmid_file}")
        pmid_list = load_pmids(args.pmid_file, load_from="file")
        logger.info(f"Find {len(pmid_list)} PMIDs")

    if search_type == "query":
        suffix = query.replace(" ", "_")
    if search_type == "pmids":
        if pmid_list:
            suffix = f"{pmid_list[0]}_total_{len(pmid_list)}"
        else:
            suffix = ""
    savepath = create_savepath(args.output, type=search_type, suffix=suffix)

    pubtator_api = PubTatorAPI(
        query=query,
        pmid_list=pmid_list,
        savepath=str(savepath),
        search_type=search_type,
        sort=args.sort,
        max_articles=args.max_articles,
        full_text=args.full_text,
        use_mesh=args.use_mesh,
        debug=args.debug,
        queue=None,
    )

    try:
        pubtator_api.run()
    except (NoArticles, EmptyInput, UnsuccessfulRequest) as e:
        logger.error(str(e))


def network_entry(args):
    from netmedex.network_core import NetworkBuilder

    debug = args.debug
    logfile_name = "network" if debug else None
    config_logger(debug, logfile_name)

    pubtator_filepath = Path(args.input)
    if args.output is None:
        savepath = pubtator_filepath.with_suffix(f".{args.format}")
    else:
        savepath = Path(args.output)
        savepath.parent.mkdir(parents=True, exist_ok=True)

    network_builder = NetworkBuilder(
        pubtator_filepath=str(pubtator_filepath),
        savepath=str(savepath),
        node_type=args.node_type,
        output_filetype=args.format,
        weighting_method=args.weighting_method,
        edge_weight_cutoff=args.cut_weight,
        pmid_weight_filepath=args.pmid_weight,
        max_edges=args.max_edges,
        community=args.community,
        debug=args.debug,
    )

    network_builder.run()


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
        choices=["xgmml", "html", "json"],
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
