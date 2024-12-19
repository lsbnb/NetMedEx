import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from netmedex.cli import main
from netmedex.network_core import NetworkBuilder
from netmedex.pubtator_core import PubTatorAPI

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
        ("qtihasiogha", "No articles found by PubTator3 API."),
        ("covid19", "Possibly too many articles. Please try more specific queries."),
    ],
)
def test_api_pubtator3_api_error(query, error_msg, tempdir, monkeypatch: pytest.MonkeyPatch):
    args = ["netmedex", "search", "-q", query, "-o", str(tempdir / "test.pubtator")]
    monkeypatch.setattr("sys.argv", args)
    with (
        mock.patch("netmedex.pubtator_core.FALLBACK_SEARCH", False),
        mock.patch("netmedex.cli.logger") as mock_logger,
    ):
        main()
        mock_logger.error.assert_called_with(error_msg)


def test_api_pubtator3_api_fallback_search(tempdir, monkeypatch: pytest.MonkeyPatch):
    args = [
        "netmedex",
        "search",
        "-q",
        "covid19",
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
                "search_type": "query",
                "sort": "date",
                "max_articles": 100,
                "full_text": True,
                "use_mesh": False,
                "debug": False,
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
                "search_type": "query",
                "sort": "score",
                "max_articles": 100,
                "full_text": False,
                "use_mesh": True,
                "debug": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-q", "foo"],
            {
                "query": "foo",
                "pmid_list": None,
                "savepath": "query_foo.pubtator",
                "search_type": "query",
                "sort": "date",
                "max_articles": 1000,
                "full_text": False,
                "use_mesh": False,
                "debug": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-p", "123,456", "-o", "bar"],
            {
                "query": None,
                "pmid_list": ["123", "456"],
                "savepath": "bar",
                "search_type": "pmids",
                "sort": "date",
                "max_articles": 1000,
                "full_text": False,
                "use_mesh": False,
                "debug": False,
                "queue": None,
            },
        ),
        (
            ["netmedex", "search", "-p", "123,456", "--full_text"],
            {
                "query": None,
                "pmid_list": ["123", "456"],
                "savepath": "pmids_123_total_2.pubtator",
                "search_type": "pmids",
                "sort": "date",
                "max_articles": 1000,
                "full_text": True,
                "use_mesh": False,
                "debug": False,
                "queue": None,
            },
        ),
        (
            [
                "netmedex",
                "search",
                "-f",
                "./tests/test_data/pmid_list.txt",
                "--max_articles",
                "10000",
            ],
            {
                "query": None,
                "pmid_list": ["34205807", "34895069", "35883435"],
                "savepath": "pmids_34205807_total_3.pubtator",
                "search_type": "pmids",
                "sort": "date",
                "max_articles": 10000,
                "full_text": False,
                "use_mesh": False,
                "debug": False,
                "queue": None,
            },
        ),
    ],
)
def test_pubtator_api_main(args, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with mock.patch("netmedex.pubtator_core.PubTatorAPI") as mock_pipeline:
        main()
        mock_pipeline.assert_called_once_with(
            query=expected["query"],
            pmid_list=expected["pmid_list"],
            savepath=expected["savepath"],
            search_type=expected["search_type"],
            sort=expected["sort"],
            max_articles=expected["max_articles"],
            use_mesh=expected["use_mesh"],
            full_text=expected["full_text"],
            debug=expected["debug"],
            queue=expected["queue"],
        )


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


def test_write_output_none():
    open_mock = mock.mock_open()
    args = {
        "query": None,
        "pmid_list": ["123", "456"],
        "savepath": None,
        "search_type": "pmids",
        "sort": "date",
        "max_articles": 1000,
        "full_text": True,
        "use_mesh": False,
        "debug": False,
        "queue": None,
    }
    with mock.patch("builtins.open", create=True):
        pubtator3_api = PubTatorAPI(**args)
        pubtator3_api._write_results("foo")
        open_mock.assert_not_called()


@pytest.mark.parametrize(
    "output,savepath,use_mesh,expected",
    [("foo", "bar.pubtator", False, "foo"), ("foo", "bar.pubtator", True, "foo")],
)
def test_write_output(output, savepath, use_mesh, expected):
    open_mock = mock.mock_open()
    args = {
        "query": None,
        "pmid_list": ["123", "456"],
        "savepath": savepath,
        "search_type": "pmids",
        "sort": "date",
        "max_articles": 1000,
        "full_text": True,
        "use_mesh": use_mesh,
        "debug": False,
        "queue": None,
    }
    with (
        mock.patch("builtins.open", open_mock, create=True),
        mock.patch("netmedex.pubtator_core.logger") as mock_logger,
    ):
        pubtator3_api = PubTatorAPI(**args)
        pubtator3_api._write_results(output)
        if use_mesh:
            open_mock.return_value.writelines.assert_any_call(["##USE-MESH-VOCABULARY", "\n"])
        open_mock.return_value.writelines.assert_any_call(output)
        mock_logger.info.assert_called_with(f"Save to {savepath}")


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
    network_builder = NetworkBuilder(**network_cli_args[args])
    network_builder.run()
