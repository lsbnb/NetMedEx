import io

import pytest

from netmedex.pubtator_parser import HEADER_SYMBOL, PubTatorIO


@pytest.mark.parametrize(
    "data,expected",
    [
        (f"{HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", "USE-MESH-VOCABULARY"),
        (f"{HEADER_SYMBOL + HEADER_SYMBOL}USE-MESH-VOCABULARY\nfoobar", "##USE-MESH-VOCABULARY"),
    ],
)
def test_parse_header(data, expected):
    header_result = PubTatorIO._parse_header(io.StringIO(data))
    assert expected in header_result.headers


@pytest.mark.parametrize(
    "data,non_expected",
    [
        (f"{HEADER_SYMBOL[0]}USE-MESH-VOCABULARY\nfoobar", "USE-MESH-VOCABULARY"),
    ],
)
def test_parse_header_invalid(data, non_expected):
    header_result = PubTatorIO._parse_header(io.StringIO(data))
    assert non_expected not in header_result.headers
