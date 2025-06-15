import asyncio
import json
from pathlib import Path
from queue import Queue
from typing import Any

import pytest

from netmedex.cli_utils import load_pmids
from netmedex.exceptions import EmptyInput
from netmedex.pubtator import PubTatorAPI


@pytest.fixture(scope="module")
def paths(data_dir) -> dict[str, Path]:
    """Collect test data paths once per module."""
    return {
        "json_abstract": data_dir / "22439397_abstract_240916.json",
        "json_full": data_dir / "22429397_full_240916.json",
        "pubtator": data_dir / "22429397_abstract_240916.pubtator",
        "pmids": data_dir / "pmid_list.txt",
    }


@pytest.fixture()
def stub_network(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]):
    async def _fake_send_cite_query(query: str, session: Any):
        # header + 3 PMIDs
        return (
            "#PMID\tTitle\tJournal\n"
            "1111\tDummy title A\tJ1\n"
            "2222\tDummy title B\tJ2\n"
            "3333\tDummy title C\tJ3"
        )

    monkeypatch.setattr(
        "netmedex.pubtator.send_cite_query",
        _fake_send_cite_query,
        raising=True,
    )

    async def _fake_send_publication_request(
        pmid_string: str,
        article_id_type: str,
        format: str,
        full_text: bool,
        session: Any,
    ):
        if full_text:
            return json.load(paths["json_full"].open())
        else:
            if format == "pubtator":
                return paths["pubtator"].read_text()
            elif format == "biocjson":
                return json.load(paths["json_abstract"].open())
        return ""

    monkeypatch.setattr(
        "netmedex.pubtator.send_publication_request",
        _fake_send_publication_request,
        raising=True,
    )

    yield


def test_empty_input():
    with pytest.raises(EmptyInput):
        PubTatorAPI(query="  ", return_pmid_only=True).run()


# NOTE: Currently use `search` instead of `cite`
# def test_no_articles(monkeypatch: pytest.MonkeyPatch):
#     async def _fake_send_cite_query(query: str, session: Any):
#         return ""

#     monkeypatch.setattr(
#         "netmedex.pubtator.send_cite_query",
#         _fake_send_cite_query,
#         raising=True,
#     )

#     with pytest.raises(NoArticles):
#         PubTatorAPI(query="Dummy String", sort="date", return_pmid_only=True).run()


# def test_run_returns_only_pmids(stub_network):
#     collection = PubTatorAPI(query="test", sort="date", return_pmid_only=True).run()

#     assert collection.metadata["pmid_list"] == ["1111", "2222", "3333"]
#     assert collection.articles == []


# def test_run_full_pipeline(stub_network):
#     collection = PubTatorAPI(query="test", sort="date").run()

#     # Network stubs return the article with PMID 22429397.
#     assert collection.metadata["pmid_list"] == ["1111", "2222", "3333"]


def test_batch_publication_queue(stub_network):
    pmids = [str(i) for i in range(1, 102)]
    queue: Queue[str | None] = Queue()

    api = PubTatorAPI(pmid_list=pmids, queue=queue)
    asyncio.run(api.batch_publication_search(pmids))

    progress: list[str | None] = []
    while True:
        msg = queue.get()
        progress.append(msg)
        if msg is None:
            break

    assert progress == ["get/100/101", "get/101/101", "get/101/101", None]


def test_load_pmids_file(paths):
    assert load_pmids(paths["pmids"], load_from="file") == [
        "34205807",
        "34895069",
        "35883435",
    ]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("34205807, 34895069, 35883435", ["34205807", "34895069", "35883435"]),
        ("34205807,34895069,35883435", ["34205807", "34895069", "35883435"]),
        ("foo,bar,foobar", []),
        ("", []),
        (None, []),
    ],
)
def test_load_pmids_string(query: str | None, expected: list[str]):
    assert load_pmids(query, load_from="string") == expected
