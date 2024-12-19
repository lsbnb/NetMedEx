import pytest

from netmedex.stemmers import s_stemmer


@pytest.mark.parametrize(
    "input,expected",
    [
        ("", ""),
        ("abdominal diseases", "abdominal disease"),
        ("reactive oxygen species", "reactive oxygen species"),
    ],
)
def test_s_stemmer(input, expected):
    output = s_stemmer(input)
    assert output == expected, f"result: {output}, expected: {expected}"
