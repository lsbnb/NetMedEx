import json
from pathlib import Path

import pytest

from netmedex.biocjson_parser import biocjson_to_pubtator


@pytest.fixture(scope="module")
def paths(request):
    test_dir = Path(request.config.rootdir) / "tests/test_data"
    paths = {
        "abstract_json": test_dir / "pubtator3.22439397_abstract_240916.json",
        "full_json": test_dir / "pubtator3.22429397_full_240916.json",
        "abstract_pubtator": test_dir / "22429397_abstract_240916.pubtator",
        "full_pubtator": test_dir / "22429397_full_240916.pubtator",
        "full_to_abstract_pubtator": test_dir / "22429397_full_to_abstract_240916.pubtator",
    }
    return paths


def test_abstract_to_abstract_conversion(paths):
    with open(paths["abstract_json"]) as f:
        data = json.load(f)

    result = biocjson_to_pubtator(data, retain_ori_text=True, only_abstract=True)

    with open(paths["abstract_pubtator"]) as f:
        expected = f.read()

    assert result == expected


def test_full_to_abstract_conversion(paths):
    with open(paths["full_json"]) as f:
        data = json.load(f)

    result = biocjson_to_pubtator(data, retain_ori_text=True, only_abstract=True)

    with open(paths["full_to_abstract_pubtator"]) as f:
        expected = f.read()

    assert result == expected


def test_full_conversion(paths):
    with open(paths["full_json"]) as f:
        data = json.load(f)

    result = biocjson_to_pubtator(data, retain_ori_text=True, only_abstract=False)

    with open(paths["full_pubtator"]) as f:
        expected = f.read()

    assert result == expected
