import json
from pathlib import Path

import pytest

from pubtoscape.biocjson_parser import (convert_to_pubtator,
                                        get_biocjson_annotations)
from pubtoscape.exceptions import EmptyInput, NoArticles
from pubtoscape.pubtator3_api_cli import (batch_publication_query, load_pmids,
                                          parse_cite_response,
                                          run_query_pipeline,
                                          send_publication_query,
                                          send_search_query)

TESTDATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="module")
def paths():
    filepaths = {"json": TESTDATA_DIR / "pubtator3.37026113_240614.json",
                 "pubtator-std_relation-std": TESTDATA_DIR / "pubtator3.37026113_standardized_std-relation_240614.pubtator",
                 "pubtator-std_relation-ori": TESTDATA_DIR / "pubtator3.37026113_standardized_ori-relation_240614.pubtator",
                 "pubtator": TESTDATA_DIR / "pubtator3.37026113_240614.pubtator",
                 "tsv": TESTDATA_DIR / "cite_tsv.tsv",
                 "pmids": TESTDATA_DIR / "pmid_list.txt"}
    return filepaths


def test_send_search_query_search():
    query = "N-dimethylnitrosamine and Metformin"
    res = send_search_query(query, type="search")

    expected = 130
    if res.status_code == 200:
        total_articles = res.json()["count"]
    else:
        total_articles = None

    assert total_articles >= expected


def test_parse_cite_response(paths):
    filepath = paths["tsv"]
    expected = ["38229736", "38173127", "38132876"]
    with open(filepath) as f:
        pmid_list = parse_cite_response(f.read())

    assert pmid_list == expected


def test_send_search_query_cite():
    query = "N-dimethylnitrosamine and Metformin"
    res = send_search_query(query, type="cite")
    expected = 130
    if res.status_code == 200:
        total_articles = len(parse_cite_response(res.text))
    else:
        total_articles = None

    assert total_articles >= expected


def test_parse_biocjson_response(paths):
    filepath = paths["json"]
    with open(filepath) as f:
        content = json.load(f)["PubTator3"][0]

    expected_len = 33
    annotation_list = get_biocjson_annotations(content, retain_ori_text=False)

    assert len(annotation_list) == expected_len


def test_full_text():
    pmid = "37026113"
    res = send_publication_query(pmid, type="pmids", format="biocjson", full_text=True)

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
        cjson = convert_to_pubtator(json.load(cjson), retain_ori_text=True, role_type="identifier")
        assert cjson == pubtator


def test_batch_standardized_annotations(paths):
    test_filepath = paths["pubtator-std_relation-std"]
    output = batch_publication_query(["37026113"], type="pmids", full_text=False, use_mesh=True)
    result = convert_to_pubtator(output[0], retain_ori_text=False)

    with open(test_filepath) as f:
        assert result == f.read()


def test_empty_input():
    with pytest.raises(EmptyInput):
        run_query_pipeline(None, None, "query")


def test_no_articles():
    with pytest.raises(NoArticles):
        run_query_pipeline("qwrsadga", None, "query")


def test_load_pmids(paths):
    pmid_list = load_pmids(paths["pmids"], load_from="file")

    assert pmid_list == ["34205807", "34895069", "35883435"]
