import pytest
from pubtoscape.biocjson_parser import convert_to_pubtator
from pathlib import Path
import json

TESTDATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="module")
def paths():
    filepaths = {
        "abstract_json": TESTDATA_DIR / "pubtator3.22439397_abstract_240916.json",
        "full_json": TESTDATA_DIR / "pubtator3.22429397_full_240916.json",
        "abstract_pubtator": TESTDATA_DIR / "22429397_abstract_240916.pubtator",
        "full_pubtator": TESTDATA_DIR / "22429397_full_240916.pubtator",
        "full_to_abstract_pubtator": TESTDATA_DIR / "22429397_full_to_abstract_240916.pubtator",
    }
    return filepaths


def test_abstract_to_abstract_conversion(paths):
    with open(paths["abstract_json"], "r") as f:
        data = json.load(f)

    result = convert_to_pubtator(data, retain_ori_text=True, only_abstract=True)

    with open(paths["abstract_pubtator"], "r") as f:
        expected = f.read()

    assert result == expected


def test_full_to_abstract_conversion(paths):
    with open(paths["full_json"], "r") as f:
        data = json.load(f)

    result = convert_to_pubtator(data, retain_ori_text=True, only_abstract=True)

    with open(paths["full_to_abstract_pubtator"], "r") as f:
        expected = f.read()

    assert result == expected


def test_full_conversion(paths):
    with open(paths["full_json"], "r") as f:
        data = json.load(f)

    result = convert_to_pubtator(data, retain_ori_text=True, only_abstract=False)

    with open(paths["full_pubtator"], "r") as f:
        expected = f.read()

    assert result == expected
