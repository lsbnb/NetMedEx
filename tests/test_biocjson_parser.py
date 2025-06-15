import json
from dataclasses import asdict

import pytest

from netmedex.biocjson_parser import biocjson_to_pubtator


@pytest.fixture(scope="module")
def paths(data_dir):
    paths = {
        "abstract_json": data_dir / "22439397_abstract_240916.json",
        "full_json": data_dir / "22429397_full_240916.json",
        "abstract_parsed": data_dir / "22439397_abstract_PubTatorArticle_240916.json",
        "full_parsed": data_dir / "22439397_full_PubTatorArticle_240916.json",
    }
    return paths


def test_abstract_parsing(paths):
    data = json.load(open(paths["abstract_json"]))
    expected = json.load(open(paths["abstract_parsed"]))

    result = asdict(biocjson_to_pubtator(data, full_text=False)[0])

    assert result == expected


def test_full_to_abstract_conversion(paths):
    data = json.load(open(paths["full_json"]))
    expected = json.load(open(paths["full_parsed"]))

    result = asdict(biocjson_to_pubtator(data, full_text=True)[0])

    assert result == expected
