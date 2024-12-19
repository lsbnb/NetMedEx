import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

TEMPDIR = TemporaryDirectory()
SAVEDIR = Path(TEMPDIR.name) if os.getenv("SAVEDIR") is None else Path(os.getenv("SAVEDIR"))
MAX_ARTICLES = 1000
DATA_FILENAME = {
    "graph": "G.pkl",
    "xgmml": "output.xgmml",
    "html": "output.html",
    "pubtator": "output.pubtator",
    "edge_info": "output.csv",
}
visibility = SimpleNamespace(visible={"visibility": "visible"}, hidden={"visibility": "hidden"})
display = SimpleNamespace(block={"display": "block"}, none={"display": "none"})


def generate_session_id():
    return str(uuid4())


def get_data_savepath(session_id: str):
    savepath = {}
    savedir = SAVEDIR / session_id
    savedir.mkdir(parents=True, exist_ok=True)
    for file, filepath in DATA_FILENAME.items():
        savepath[file] = str(savedir / filepath)
    return savepath


def clean_up_files():
    try:
        TEMPDIR.cleanup()
    except Exception:
        pass
