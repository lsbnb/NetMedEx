from __future__ import annotations

# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import os
import sys
from pathlib import Path

from netmedex.utils import config_logger

logger = logging.getLogger(__name__)


def _init_cli_llm_client(args, usage_context: str):
    from dotenv import load_dotenv
    from webapp.llm import LLMClient

    load_dotenv()
    llm_client = LLMClient()

    provider = args.llm_provider or llm_client.provider or "openai"
    if provider not in {"openai", "google", "local"}:
        logger.error(f"Unsupported LLM provider: {provider}")
        logger.error("Supported providers: openai, google, local")
        sys.exit(1)

    base_url = args.llm_base_url or os.getenv("OPENAI_BASE_URL")
    model = args.llm_model
    api_key = args.llm_api_key

    if provider == "openai":
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error(
                f"{usage_context} with OpenAI provider requires OPENAI_API_KEY (or --llm_api_key)."
            )
            sys.exit(1)
    elif provider == "google":
        api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv(
            "OPENAI_API_KEY"
        )
        if not api_key:
            logger.error(
                f"{usage_context} with Google provider requires GEMINI_API_KEY "
                "(or GOOGLE_API_KEY / --llm_api_key)."
            )
            sys.exit(1)
    else:
        api_key = api_key or os.getenv("LOCAL_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "local-dummy-key"
        base_url = base_url or os.getenv("LOCAL_LLM_BASE_URL") or "http://localhost:11434/v1"
        if not base_url:
            logger.error(
                f"{usage_context} with local provider requires LOCAL_LLM_BASE_URL "
                "(or --llm_base_url)."
            )
            sys.exit(1)

    llm_client.initialize_client(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
    )

    if not llm_client.client:
        logger.error("Failed to initialize LLM client.")
        sys.exit(1)

    logger.info(
        f"LLM client initialized for {usage_context} "
        f"(provider: {llm_client.provider}, model: {llm_client.model}, base_url: {llm_client.base_url})"
    )
    return llm_client


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
        use_llm_search = bool(
            args.ai_search
            or args.llm_provider
            or args.llm_api_key
            or args.llm_model
            or args.llm_base_url
        )
        if use_llm_search:
            try:
                llm_client = _init_cli_llm_client(args, usage_context="query translation")
                translated_query = llm_client.translate_query_to_boolean(query)
                if translated_query and not str(translated_query).startswith("Error:"):
                    logger.info(f"AI search query translated: {translated_query}")
                    query = translated_query
                else:
                    logger.warning("AI search translation returned empty/invalid result. Using original query.")
            except ImportError as e:
                logger.error(f"Failed to import required libraries for AI search: {e}")
                logger.error("Please install: pip install openai python-dotenv requests")
                sys.exit(1)
            except Exception as e:
                logger.warning(f"AI search translation failed, using original query: {e}")
        suffix = query.replace(" ", "_").replace('"', "")
        savepath = args.output if args.output is not None else f"./query_{suffix}.pubtator"
    else:
        if args.pmids is not None:
            pmid_list = load_pmids(args.pmids, load_from="string")
            logger.info(f"Found {len(pmid_list)} PMIDs")
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
    llm_client = None
    if args.edge_method == "semantic":
        try:
            llm_client = _init_cli_llm_client(args, usage_context="semantic edge extraction")
        except ImportError as e:
            logger.error(f"Failed to import required libraries for semantic analysis: {e}")
            logger.error("Please install: pip install openai python-dotenv requests")
            sys.exit(1)
    
    graph_builder = PubTatorGraphBuilder(
        node_type=args.node_type,
        edge_method=args.edge_method,
        llm_client=llm_client,
        semantic_threshold=args.semantic_threshold,
    )
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


def _sorted_pmids(pmids):
    return sorted(pmids, key=lambda x: (not str(x).isdigit(), int(x) if str(x).isdigit() else str(x)))


def _collect_pmid_edges(G):
    pmid_edges = {}
    for u, v, data in G.edges(data=True):
        relations = data.get("relations", {})
        if isinstance(relations, dict):
            relation_pmids = relations.keys()
        else:
            relation_pmids = []

        fallback_pmids = data.get("pmids", [])
        if isinstance(fallback_pmids, str):
            fallback_pmids = [fallback_pmids]

        all_pmids = set(str(p) for p in relation_pmids) | set(str(p) for p in fallback_pmids)
        for pmid in all_pmids:
            pmid_edges.setdefault(pmid, []).append(
                {
                    "source": str(u),
                    "target": str(v),
                    "relations": sorted(relations.get(pmid, [])) if isinstance(relations, dict) else [],
                }
            )
    return pmid_edges


def chat_entry(args):
    from netmedex.chat import ChatSession
    from netmedex.cli_utils import load_pmids
    from netmedex.graph import load_graph
    from netmedex.graph_rag import GraphRetriever
    from netmedex.node_rag import GraphNode, NodeRAG
    from netmedex.rag import AbstractDocument, AbstractRAG

    debug = args.debug
    logfile_name = "chat" if debug else None
    config_logger(debug, logfile_name)

    graph_path = Path(args.graph)
    if not graph_path.exists():
        logger.error(f"Graph file not found: {graph_path}")
        sys.exit(1)

    if graph_path.suffix not in {".pickle", ".pkl"}:
        logger.error("Chat currently requires a pickle graph file (.pickle or .pkl).")
        logger.error("Please build network with: netmedex network ... -f pickle")
        sys.exit(1)

    try:
        G = load_graph(str(graph_path))
    except Exception as e:
        logger.error(f"Failed to load graph: {e}")
        sys.exit(1)

    if args.pmids is not None and args.pmid_file is not None:
        logger.error("Please specify only one of: --pmids, --pmid_file")
        sys.exit(1)

    try:
        llm_client = _init_cli_llm_client(args, usage_context="chat")
    except ImportError as e:
        logger.error(f"Failed to import required libraries for chat: {e}")
        logger.error("Please install: pip install openai python-dotenv requests chromadb")
        sys.exit(1)

    pmid_titles = {str(k): v for k, v in G.graph.get("pmid_title", {}).items()}
    pmid_abstracts = {str(k): v for k, v in G.graph.get("pmid_abstract", {}).items()}
    all_pmids = _sorted_pmids(set(pmid_titles.keys()) | set(pmid_abstracts.keys()))
    if not all_pmids:
        logger.error("No PMID metadata found in graph. Rebuild graph from PubTator input before chat.")
        sys.exit(1)

    selected_pmids = all_pmids
    if args.pmids is not None:
        selected_pmids = load_pmids(args.pmids, load_from="string")
    elif args.pmid_file is not None:
        selected_pmids = load_pmids(args.pmid_file, load_from="file")

    selected_pmids = [str(p) for p in selected_pmids if str(p) in set(all_pmids)]
    selected_pmids = _sorted_pmids(selected_pmids)
    if args.max_pmids and args.max_pmids > 0:
        selected_pmids = selected_pmids[: args.max_pmids]

    if not selected_pmids:
        logger.error("No valid PMIDs selected for chat context.")
        sys.exit(1)

    pmid_edges = _collect_pmid_edges(G)
    documents = []
    for pmid in selected_pmids:
        documents.append(
            AbstractDocument(
                pmid=pmid,
                title=pmid_titles.get(pmid, f"PMID {pmid}"),
                abstract=pmid_abstracts.get(pmid, "Abstract not available."),
                entities=[],
                edges=pmid_edges.get(pmid, []),
            )
        )

    rag_system = AbstractRAG(llm_client)
    indexed_count = rag_system.index_abstracts(documents)

    node_rag = None
    try:
        node_rag = NodeRAG(llm_client)
        graph_nodes = []
        for node_id, data in G.nodes(data=True):
            graph_nodes.append(
                GraphNode(
                    node_id=str(node_id),
                    name=str(data.get("name", node_id)),
                    type=str(data.get("type", "Entity")),
                    metadata=data,
                )
            )
        node_rag.index_nodes(graph_nodes)
    except Exception as e:
        logger.warning(f"Node semantic retrieval disabled: {e}")

    graph_retriever = GraphRetriever(G, node_rag=node_rag)
    session = ChatSession(
        rag_system,
        llm_client,
        graph_retriever=graph_retriever,
        max_history=args.max_history,
    )

    logger.info(
        f"Hybrid RAG chat ready with {indexed_count} abstracts from {graph_path} "
        f"(provider={llm_client.provider}, model={llm_client.model})"
    )

    if args.query:
        result = session.send_message(
            args.query,
            top_k=args.top_k,
            session_language=args.session_language,
        )
        if result["success"]:
            print(result["message"])
            if result.get("sources"):
                print(f"\nSources: {', '.join(result['sources'])}")
            return
        logger.error(result.get("error", "Unknown chat error"))
        sys.exit(1)

    print(
        "Hybrid RAG CLI chat started. Type 'exit' to quit, '/clear' to clear history, '/stats' for session stats."
    )
    while True:
        try:
            user_input = input("chat> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input == "/clear":
            session.clear()
            print("History cleared.")
            continue
        if user_input == "/stats":
            stats = session.get_stats()
            print(
                "Stats: "
                f"messages={stats['message_count']}, "
                f"user={stats['user_messages']}, "
                f"assistant={stats['assistant_messages']}, "
                f"indexed_pmids={stats['indexed_pmids']}"
            )
            continue

        result = session.send_message(
            user_input,
            top_k=args.top_k,
            session_language=args.session_language,
        )
        if result["success"]:
            print(f"\n{result['message']}")
            if result.get("sources"):
                print(f"\nSources: {', '.join(result['sources'])}")
            print("")
        else:
            print(f"Error: {result.get('error', 'Unknown chat error')}")


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

    chat_subparser = subparser.add_parser(
        "chat",
        parents=[get_chat_parser()],
        help="Chat with a pickled graph via Hybrid RAG",
    )
    chat_subparser.set_defaults(entry_func=chat_entry)

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
        "--ai_search",
        action="store_true",
        help="Enable LLM-powered natural language to PubTator boolean query translation.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information",
    )
    _add_llm_parser_args(parser, help_context="search query translation")

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
    parser.add_argument(
        "--edge_method",
        choices=["co-occurrence", "semantic", "relation"],
        default="co-occurrence",
        help="Method for edge construction: "
             "co-occurrence (all co-mentions, fast), "
             "semantic (LLM-analyzed relationships, balanced), "
             "relation (BioREx annotations only, precise) (default: co-occurrence)",
    )
    parser.add_argument(
        "--semantic_threshold",
        type=float,
        default=0.5,
        help="Minimum confidence score for semantic edges, range 0-1 (default: 0.5). "
             "Only used when --edge_method=semantic",
    )
    _add_llm_parser_args(parser, help_context="semantic edge extraction")

    return parser


def _add_llm_parser_args(parser, help_context: str):
    parser.add_argument(
        "--llm_provider",
        choices=["openai", "google", "local"],
        default=None,
        help=f"LLM provider for {help_context} (default: read from LLM_PROVIDER/.env).",
    )
    parser.add_argument(
        "--llm_api_key",
        default=None,
        help=f"LLM API key override for {help_context}.",
    )
    parser.add_argument(
        "--llm_model",
        default=None,
        help=f"LLM model override for {help_context}.",
    )
    parser.add_argument(
        "--llm_base_url",
        default=None,
        help=f"LLM base URL override for {help_context}.",
    )


def get_chat_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-g",
        "--graph",
        required=True,
        help="Path to pickled graph (.pickle/.pkl) generated by `netmedex network -f pickle`.",
    )
    parser.add_argument(
        "-q",
        "--query",
        default=None,
        help="One-shot question. If omitted, starts interactive chat mode.",
    )
    parser.add_argument(
        "-p",
        "--pmids",
        default=None,
        type=str,
        help="Optional PMID subset for chat context (comma-separated).",
    )
    parser.add_argument(
        "-f",
        "--pmid_file",
        default=None,
        help="Optional file containing PMIDs (one per line) to limit chat context.",
    )
    parser.add_argument(
        "--top_k",
        type=int,
        default=5,
        help="Top-k abstracts for retrieval when document set is large (default: 5).",
    )
    parser.add_argument(
        "--max_pmids",
        type=int,
        default=0,
        help="Maximum PMIDs to load from graph context (default: 0 = all).",
    )
    parser.add_argument(
        "--session_language",
        default="English",
        help="Target language for responses (default: English).",
    )
    parser.add_argument(
        "--max_history",
        type=int,
        default=10,
        help="Maximum chat history messages to keep (default: 10).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information.",
    )
    _add_llm_parser_args(parser, help_context="chat")
    return parser


if __name__ == "__main__":
    main()
