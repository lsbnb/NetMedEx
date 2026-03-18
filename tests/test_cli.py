import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from netmedex.cli import main
from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_parser import PubTatorIO

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(scope="module")
def tempdir():
    with TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@pytest.fixture(scope="module")
def paths(request):
    test_dir = Path(request.config.rootdir) / "tests/test_data"
    return {"simple": test_dir / "6_nodes_3_clusters_mesh.pubtator"}


@pytest.fixture(scope="module")
def network_cli_args(paths):
    args = {
        "pubtator_filepath": paths["simple"],
        "savepath": None,
        "node_type": "all",
        "output_filetype": "html",
        "weighting_method": "freq",
        "edge_weight_cutoff": 1,
        "pmid_weight_filepath": None,
        "max_edges": 0,
        "community": False,
        "debug": False,
    }
    return {
        "args_basic": args,
        "args_community": {**args, "community": True},
        "args_mesh_only": {**args, "node_type": "mesh"},
        "args_relation_only": {**args, "node_type": "relation"},
        "args_npmi": {**args, "weighting_method": "npmi"},
        "args_weight": {**args, "edge_weight_cutoff": 20},
        "args_xgmml": {**args, "output_filetype": "xgmml"},
    }


@pytest.mark.parametrize(
    "query,error_msg",
    [
        ("", "Your search cannot be empty."),
        ("qtihasioghasaoi", "No articles found by PubTator3 API."),
        # ("chuan mu tong", "Possibly too many articles. Please try more specific queries."),  # Disable this because requesting by `cite` isn't used anymore
    ],
)
def test_api_pubtator3_api_error(query, error_msg, tempdir, monkeypatch: pytest.MonkeyPatch):
    args = [
        "netmedex",
        "search",
        "-q",
        query,
        "-o",
        str(tempdir / "test.pubtator"),
        "--max_articles",
        "10",
    ]
    monkeypatch.setattr("sys.argv", args)
    with (
        mock.patch("netmedex.pubtator.FALLBACK_SEARCH", False),
        mock.patch("netmedex.cli.logger") as mock_logger,
    ):
        main()
        mock_logger.error.assert_called_with(error_msg)


def test_api_pubtator3_api_fallback_search(tempdir, monkeypatch: pytest.MonkeyPatch):
    args = [
        "netmedex",
        "search",
        "-q",
        "COVID-19 AND PON1",
        "-o",
        str(tempdir / "test.pubtator"),
        "--max_articles",
        "10",
    ]
    monkeypatch.setattr("sys.argv", args)
    main()


@pytest.mark.parametrize(
    "args,expected",
    [
        (
            [
                "netmedex",
                "search",
                "-q",
                "foo",
                "-o",
                "bar",
                "--max_articles",
                "100",
                "--full_text",
                "-s",
                "date",
            ],
            {
                "query": "foo",
                "pmid_list": None,
                "savepath": "bar",
                "sort": "date",
                "max_articles": 100,
                "full_text": True,
                "queue": None,
            },
        ),
        (
            [
                "netmedex",
                "search",
                "-q",
                "foo",
                "-o",
                "bar",
                "--max_articles",
                "100",
                "--use_mesh",
                "-s",
                "score",
            ],
            {
                "query": "foo",
                "pmid_list": None,
                "savepath": "bar",
                "sort": "score",
                "max_articles": 100,
                "full_text": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-q", "foo"],
            {
                "query": "foo",
                "pmid_list": None,
                "savepath": "./query_foo.pubtator",
                "sort": "date",
                "max_articles": 1000,
                "full_text": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-p", "123,456", "-o", "bar"],
            {
                "query": None,
                "pmid_list": ["123", "456"],
                "savepath": "bar",
                "sort": "date",
                "max_articles": 1000,
                "full_text": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-p", "123,456", "--full_text"],
            {
                "query": None,
                "pmid_list": ["123", "456"],
                "savepath": "./pmids_123_total_2.pubtator",
                "sort": "date",
                "max_articles": 1000,
                "full_text": True,
                "queue": None,
            },
        ),
        (
            [
                "netmedex",
                "search",
                "-f",
                str(Path(__file__).parent / "test_data/pmid_list.txt"),
                "--max_articles",
                "10000",
            ],
            {
                "query": None,
                "pmid_list": ["34205807", "34895069", "35883435"],
                "savepath": "./pmids_34205807_total_3.pubtator",
                "sort": "date",
                "max_articles": 10000,
                "full_text": False,
                "queue": None,
            },
        ),
    ],
)
def test_pubtator_api_main(args, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with (
        mock.patch("netmedex.pubtator.PubTatorAPI") as mock_pipeline,
        mock.patch("netmedex.cli.open", mock.mock_open()) as mocked_open,
    ):
        main()
        mock_pipeline.assert_called_once_with(
            query=expected["query"],
            pmid_list=expected["pmid_list"],
            sort=expected["sort"],
            request_format="biocjson",
            max_articles=expected["max_articles"],
            full_text=expected["full_text"],
            queue=expected["queue"],
        )
        mocked_open.assert_called_once_with(expected["savepath"], "w")


@pytest.mark.parametrize(
    "args",
    [
        ["netmedex", "search", "-q", ""],
        ["netmedex", "search", "-p", "   "],
    ],
)
def test_pubtator3_api_exceptions(args, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with mock.patch("netmedex.cli.logger") as mock_logger:
        main()
        mock_logger.error.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        ["netmedex", "search", "-p", "123", "-q", "bar"],
        ["netmedex", "search", "-f", "foo.txt", "-q", "bar"],
    ],
)
def test_pubtator3_api_exit(args, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit):
        with mock.patch("netmedex.cli.logger") as mock_logger:
            main()
            mock_logger.info.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        "args_basic",
        "args_community",
        "args_mesh_only",
        "args_relation_only",
        "args_npmi",
        "args_weight",
        "args_xgmml",
    ],
)
def test_network_cli(args, paths, tempdir, network_cli_args):
    input_args = network_cli_args[args]
    network_builder = PubTatorGraphBuilder(node_type=input_args["node_type"])
    collection = PubTatorIO.parse(input_args["pubtator_filepath"])
    network_builder.add_collection(collection)
    network_builder.build(
        pmid_weights=input_args["pmid_weight_filepath"],
        weighting_method=input_args["weighting_method"],
        edge_weight_cutoff=input_args["edge_weight_cutoff"],
        community=input_args["community"],
        max_edges=input_args["max_edges"],
    )


def test_network_cli_accepts_llm_provider_flags(paths):
    from netmedex.cli import parse_args

    parsed = parse_args(
        [
            "network",
            "-i",
            str(paths["simple"]),
            "--edge_method",
            "semantic",
            "--llm_provider",
            "google",
            "--llm_api_key",
            "test-key",
            "--llm_model",
            "gemini-2.0-flash",
            "--llm_base_url",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ]
    )
    assert parsed.llm_provider == "google"
    assert parsed.llm_api_key == "test-key"
    assert parsed.llm_model == "gemini-2.0-flash"
    assert parsed.llm_base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_search_cli_accepts_llm_provider_flags():
    from netmedex.cli import parse_args

    parsed = parse_args(
        [
            "search",
            "-q",
            "natural language query",
            "--ai_search",
            "--llm_provider",
            "google",
            "--llm_api_key",
            "test-key",
            "--llm_model",
            "gemini-2.0-flash",
            "--llm_base_url",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ]
    )
    assert parsed.ai_search is True
    assert parsed.llm_provider == "google"
    assert parsed.llm_api_key == "test-key"
    assert parsed.llm_model == "gemini-2.0-flash"
    assert parsed.llm_base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_search_cli_ai_search_uses_provider_aware_translation(monkeypatch: pytest.MonkeyPatch):
    args = [
        "netmedex",
        "search",
        "-q",
        "中文自然語言查詢",
        "--ai_search",
        "--llm_provider",
        "local",
        "--llm_base_url",
        "http://localhost:11434/v1",
    ]
    monkeypatch.setattr("sys.argv", args)

    fake_collection = mock.MagicMock()
    fake_collection.to_pubtator_str.return_value = "fake-pubtator-content"
    fake_llm_client = mock.MagicMock()
    fake_llm_client.translate_query_to_boolean.return_value = '"osteoporosis" AND "miRNA"'

    with (
        mock.patch("netmedex.cli._init_cli_llm_client", return_value=fake_llm_client) as mock_init_llm,
        mock.patch("netmedex.pubtator.PubTatorAPI") as mock_pubtator_api,
        mock.patch("netmedex.cli.open", mock.mock_open()) as mocked_open,
    ):
        mock_pubtator_api.return_value.run.return_value = fake_collection
        main()

        mock_init_llm.assert_called_once()
        fake_llm_client.translate_query_to_boolean.assert_called_once_with("中文自然語言查詢")
        mock_pubtator_api.assert_called_once_with(
            query='"osteoporosis" AND "miRNA"',
            pmid_list=None,
            sort="date",
            request_format="biocjson",
            max_articles=1000,
            full_text=False,
            queue=None,
        )
        mocked_open.assert_called_once_with('./query_osteoporosis_AND_miRNA.pubtator', "w")


def test_network_cli_semantic_uses_provider_aware_client(monkeypatch: pytest.MonkeyPatch, paths, tempdir):
    args = [
        "netmedex",
        "network",
        "-i",
        str(paths["simple"]),
        "-o",
        str(tempdir / "semantic.html"),
        "--edge_method",
        "semantic",
        "--llm_provider",
        "local",
        "--llm_base_url",
        "http://localhost:11434/v1",
    ]
    monkeypatch.setattr("sys.argv", args)

    fake_collection = object()
    fake_graph = object()
    fake_llm_client = object()

    with (
        mock.patch("netmedex.pubtator_parser.PubTatorIO.parse", return_value=fake_collection),
        mock.patch("netmedex.cli._init_cli_llm_client", return_value=fake_llm_client) as mock_init_llm,
        mock.patch("netmedex.graph.PubTatorGraphBuilder") as mock_builder_cls,
        mock.patch("netmedex.graph.save_graph") as mock_save_graph,
    ):
        mock_builder = mock_builder_cls.return_value
        mock_builder.build.return_value = fake_graph

        main()

        mock_init_llm.assert_called_once()
        mock_builder_cls.assert_called_once_with(
            node_type="all",
            edge_method="semantic",
            llm_client=fake_llm_client,
            semantic_threshold=0.5,
        )
        mock_builder.add_collection.assert_called_once_with(fake_collection)
        mock_builder.build.assert_called_once()
        mock_save_graph.assert_called_once()


def test_chat_cli_accepts_provider_flags(paths):
    from netmedex.cli import parse_args

    parsed = parse_args(
        [
            "chat",
            "-g",
            str(paths["simple"]).replace(".pubtator", ".pickle"),
            "-q",
            "Summarize key findings",
            "--llm_provider",
            "local",
            "--llm_base_url",
            "http://localhost:11434/v1",
            "--llm_model",
            "llama3.1",
            "--max_pmids",
            "20",
            "--top_k",
            "4",
        ]
    )
    assert parsed.llm_provider == "local"
    assert parsed.llm_base_url == "http://localhost:11434/v1"
    assert parsed.llm_model == "llama3.1"
    assert parsed.max_pmids == 20
    assert parsed.top_k == 4


def test_chat_cli_one_shot_uses_hybrid_rag_session(monkeypatch: pytest.MonkeyPatch, tempdir, capsys):
    graph_path = tempdir / "chat_graph.pkl"
    graph_path.write_text("placeholder")
    args = [
        "netmedex",
        "chat",
        "-g",
        str(graph_path),
        "-q",
        "What are the key findings?",
        "--llm_provider",
        "openai",
        "--llm_api_key",
        "sk-test",
    ]
    monkeypatch.setattr("sys.argv", args)

    fake_graph = mock.MagicMock()
    fake_graph.graph = {
        "pmid_title": {"123": "Title A"},
        "pmid_abstract": {"123": "Abstract A"},
    }
    fake_graph.nodes.return_value = [("n1", {"name": "Node 1", "type": "Gene"})]
    fake_graph.edges.return_value = [("n1", "n2", {"relations": {"123": {"associated_with"}}})]

    fake_llm_client = mock.MagicMock(provider="openai", model="gpt-4o-mini", base_url="https://api.openai.com/v1")
    fake_rag = mock.MagicMock()
    fake_rag.index_abstracts.return_value = 1

    fake_chat_session = mock.MagicMock()
    fake_chat_session.send_message.return_value = {
        "success": True,
        "message": "Answer with [PMID:123]",
        "sources": ["123"],
    }

    with (
        mock.patch("netmedex.graph.load_graph", return_value=fake_graph),
        mock.patch("netmedex.cli._init_cli_llm_client", return_value=fake_llm_client) as mock_init,
        mock.patch("netmedex.rag.AbstractRAG", return_value=fake_rag),
        mock.patch("netmedex.node_rag.NodeRAG") as mock_node_rag_cls,
        mock.patch("netmedex.graph_rag.GraphRetriever") as mock_graph_retriever_cls,
        mock.patch("netmedex.chat.ChatSession", return_value=fake_chat_session) as mock_chat_cls,
    ):
        main()

        mock_init.assert_called_once()
        mock_node_rag_cls.assert_called_once_with(fake_llm_client)
        mock_graph_retriever_cls.assert_called_once()
        mock_chat_cls.assert_called_once()
        fake_chat_session.send_message.assert_called_once_with(
            "What are the key findings?",
            top_k=5,
            session_language="English",
        )

    captured = capsys.readouterr()
    assert "Answer with [PMID:123]" in captured.out
    assert "Sources: 123" in captured.out
