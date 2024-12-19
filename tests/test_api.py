import json
import pickle
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest import mock

import pytest
import requests_mock

from netmedex.biocjson_parser import biocjson_to_pubtator, get_biocjson_annotations
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from netmedex.pubtator_core import (
    PubTatorAPI,
    parse_cite_response,
    request_successful,
    send_publication_query,
    send_search_query,
    unsuccessful_query,
)
from netmedex.pubtator_utils import load_pmids

TESTDATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="module")
def paths():
    filepaths = {
        "json": TESTDATA_DIR / "pubtator3.37026113_240614.json",
        "json_full-text": TESTDATA_DIR / "pubtator3.22429397_full_240916.json",
        "pubtator-std_relation-std": TESTDATA_DIR
        / "pubtator3.37026113_standardized_std-relation_240614.pubtator",
        "pubtator-std_relation-ori": TESTDATA_DIR
        / "pubtator3.37026113_standardized_ori-relation_240614.pubtator",
        "pubtator": TESTDATA_DIR / "pubtator3.37026113_240614.pubtator",
        "tsv": TESTDATA_DIR / "cite_tsv.tsv",
        "pmids": TESTDATA_DIR / "pmid_list.txt",
        "query_search": TESTDATA_DIR / "search_N-dimethylnitrosamine_and_Metformin_241008.pkl",
        "query_cite": TESTDATA_DIR / "cite_N-dimethylnitrosamine_and_Metformin_241008.pkl",
    }
    return filepaths


@requests_mock.Mocker(kw="mock")
def test_send_search_query_search(paths, **kwargs):
    query = "N-dimethylnitrosamine and Metformin"

    with open(paths["query_search"], "rb") as f:
        res_json = pickle.load(f).json()

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/?text=N-dimethylnitrosamine+and+Metformin",
        status_code=200,
        json=res_json,
    )
    res = send_search_query(query, type="search")

    assert res.json()["count"] == 136


def test_api_send_search_query_search():
    query = "N-dimethylnitrosamine and Metformin"
    res = send_search_query(query, type="search")

    expected = 136
    if res.status_code == 200:
        total_articles = res.json()["count"]
    else:
        total_articles = None

    assert total_articles >= expected


@requests_mock.Mocker(kw="mock")
def test_send_search_query_cite(paths, **kwargs):
    query = "N-dimethylnitrosamine and Metformin"

    with open(paths["query_cite"], "rb") as f:
        res_text = pickle.load(f).text

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv?text=N-dimethylnitrosamine+and+Metformin",
        status_code=200,
        text=res_text,
    )

    res = send_search_query(query, type="cite")

    assert len(parse_cite_response(res.text)) == 136


def test_api_send_search_query_cite():
    query = "N-dimethylnitrosamine and Metformin"
    res = send_search_query(query, type="cite")
    expected = 130
    if res.status_code == 200:
        total_articles = len(parse_cite_response(res.text))
    else:
        total_articles = None

    assert total_articles >= expected


@requests_mock.Mocker(kw="mock")
def test_search_publication_abstract(paths, **kwargs):
    pmid = "37026113"

    with open(paths["json"]) as f:
        res_json = json.load(f)

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=37026113",
        status_code=200,
        json=res_json,
    )
    res = send_publication_query(pmid, article_id_type="pmids", format="biocjson", full_text=False)
    annotation_list = get_biocjson_annotations(res.json()["PubTator3"][0], retain_ori_text=False)

    assert len(annotation_list) == 33


@requests_mock.Mocker(kw="mock")
def test_search_publication_full_text(paths, **kwargs):
    pmid = "22429397"

    with open(paths["json_full-text"]) as f:
        res_json = json.load(f)

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=22429397&full=true",
        status_code=200,
        json=res_json,
    )

    res = send_publication_query(pmid, article_id_type="pmids", format="biocjson", full_text=True)
    annotation_list = get_biocjson_annotations(res.json()["PubTator3"][0], retain_ori_text=False)

    assert len(annotation_list) == 666


def test_api_search_publication_full_text():
    pmid = "37026113"
    res = send_publication_query(pmid, article_id_type="pmids", format="biocjson", full_text=True)

    expected_len = 379
    if res.status_code == 200:
        res = res.json()["PubTator3"][0]
        annotation_list = get_biocjson_annotations(res, retain_ori_text=False)
    else:
        annotation_list = []

    assert len(annotation_list) == expected_len


def test_biocjson_pubtator_equal(paths):
    pubtator_path = paths["pubtator"]
    biocjson_path = paths["json"]

    with open(pubtator_path) as pubtator, open(biocjson_path) as cjson:
        pubtator = pubtator.read()
        cjson = biocjson_to_pubtator(
            json.load(cjson), retain_ori_text=True, role_type="identifier"
        )
        assert cjson == pubtator


def test_parse_cite_response(paths):
    filepath = paths["tsv"]
    expected = ["38229736", "38173127", "38132876"]
    with open(filepath) as f:
        pmid_list = parse_cite_response(f.read())

    assert pmid_list == expected


def test_parse_biocjson_response(paths):
    filepath = paths["json"]
    with open(filepath) as f:
        content = json.load(f)["PubTator3"][0]

    expected_len = 33
    annotation_list = get_biocjson_annotations(content, retain_ori_text=False)

    assert len(annotation_list) == expected_len


@requests_mock.Mocker(kw="mock")
def test_use_mesh(paths, **kwargs):
    test_filepath = paths["pubtator-std_relation-std"]

    with open(paths["json"]) as f:
        res_json = json.load(f)

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=37026113",
        status_code=200,
        json=res_json,
    )

    pubtator_api = PubTatorAPI(
        query=None,
        pmid_list=["37026113"],
        savepath=None,
        search_type="pmids",
        sort="date",
        max_articles=1000,
        use_mesh=True,
        full_text=False,
        debug=False,
        queue=None,
    )
    output = pubtator_api.batch_publication_search()
    result = biocjson_to_pubtator(output[0], retain_ori_text=False)

    with open(test_filepath) as f:
        assert result == f.read()


@requests_mock.Mocker(kw="mock")
def test_batch_publication_queue(paths, **kwargs):
    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/pubtator",
        status_code=200,
        text="",
    )

    queue = Queue()
    progress = []
    expected = ["get/100/200", "get/200/200", None]
    pubtator_api = PubTatorAPI(
        query=None,
        pmid_list=[str(i) for i in range(200)],
        savepath=None,
        search_type="pmids",
        sort="date",
        max_articles=1000,
        use_mesh=False,
        full_text=False,
        debug=False,
        queue=queue,
    )
    pubtator_api.batch_publication_search()
    while True:
        result = queue.get()
        progress.append(result)
        if result is None:
            break

    assert progress == expected


@pytest.mark.parametrize(
    "args",
    [
        (None, None, "query"),
        ("   ", None, "query"),
        ([], None, "pmids"),
    ],
)
def test_empty_input(args):
    pubtator_api = PubTatorAPI(
        query=args[0],
        pmid_list=args[1],
        savepath=None,
        search_type=args[2],
        sort="date",
        max_articles=1000,
        use_mesh=False,
        full_text=False,
        debug=False,
        queue=None,
    )
    with pytest.raises(EmptyInput):
        pubtator_api.run()


@requests_mock.Mocker(kw="mock")
def test_no_articles(**kwargs):
    pubtator_api = PubTatorAPI(
        query="qwrsadga",
        pmid_list=None,
        savepath=None,
        search_type="query",
        sort="date",
        max_articles=1000,
        use_mesh=False,
        full_text=False,
        debug=False,
        queue=None,
    )
    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv?text=qwrsadga",
        status_code=200,
        text="",
    )
    with pytest.raises(NoArticles):
        pubtator_api.run()


@requests_mock.Mocker(kw="mock")
@pytest.mark.parametrize(
    "type,full_text,use_mesh,file_format",
    [
        ("query", False, False, "pubtator"),
        ("query", True, False, "biocjson"),
        ("query", False, True, "biocjson"),
        ("query", True, True, "biocjson"),
    ],
)
def test_run_query_pipeline_query(type, full_text, use_mesh, file_format, paths, **kwargs):
    with open(paths["query_cite"], "rb") as f:
        res_text = pickle.load(f).text

    kwargs["mock"].get(
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv?text=N-dimethylnitrosamine+and+Metformin",
        status_code=200,
        text=res_text,
    )

    text_or_json = {}
    if file_format == "pubtator":
        text_or_json["text"] = "foobar"
    elif file_format == "biocjson":
        text_or_json["json"] = {"PubTator3": []}

    kwargs["mock"].get(
        f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{file_format}",
        status_code=200,
        **text_or_json,
    )
    pubtator_api = PubTatorAPI(
        query="N-dimethylnitrosamine and Metformin",
        pmid_list=None,
        savepath=None,
        search_type=type,
        sort="date",
        max_articles=1000,
        use_mesh=use_mesh,
        full_text=full_text,
        debug=False,
        queue=None,
    )
    pubtator_api.run()


def test_load_pmids_file(paths):
    pmid_list = load_pmids(paths["pmids"], load_from="file")

    assert pmid_list == ["34205807", "34895069", "35883435"]


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
def test_load_pmids_string(query, expected):
    pmid_list = load_pmids(query, load_from="string")

    assert pmid_list == expected


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (200, True),
        (404, False),
        (502, False),
    ],
)
def test_request_successful(status_code, expected, **kwargs):
    res = SimpleNamespace(status_code=status_code)
    with mock.patch("netmedex.pubtator_core.logger") as mock_logger:
        assert request_successful(res) == expected
        if not expected:
            mock_logger.info.assert_called_with("Unsuccessful request")
            mock_logger.debug.assert_called_with(f"Response status code: {status_code}")


@pytest.mark.parametrize(
    "status_code,msg",
    [
        (404, "Please retry later."),
        (502, "Possibly too many articles. Please try more specific queries."),
    ],
)
def test_unsuccessful_query(status_code, msg, **kwargs):
    with pytest.raises(UnsuccessfulRequest):
        with mock.patch("netmedex.pubtator_core.logger") as mock_logger:
            unsuccessful_query(status_code)
            mock_logger.warning.assert_called_with(msg)
