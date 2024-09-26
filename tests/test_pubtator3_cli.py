import logging
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(scope="module")
def tempdir():
    with TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@pytest.mark.parametrize("query,error_message", [
    ("", "Your search cannot be empty."),
    ("qtihasiogha", "No articles found by PubTator3 API."),
    ("covid19", "Possibly too many articles. Please try more specific queries."),
])
def test_pubtator3_api_execution(query, error_message, tempdir):
    p = subprocess.run(
        [
            "pubtator3",
            "-q",
            query,
            "-o",
            tempdir / "test.pubtator",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    last_message = p.stdout.strip().split("\n")[-1]

    assert last_message == error_message, f"Expected message '{error_message}', but got '{last_message}'"

