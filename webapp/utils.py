import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

BASE_SAVEDIR = (
    Path(__file__).resolve().parents[1] / "webapp-temp"
    if (base_savedir := os.getenv("SAVEDIR")) is None
    else Path(base_savedir)
)
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
    savedir = BASE_SAVEDIR / session_id
    savedir.mkdir(parents=True, exist_ok=True)
    for file, filepath in DATA_FILENAME.items():
        savepath[file] = str(savedir / filepath)
    return savepath


def cleanup_tempdir():
    if os.getenv("SAVEDIR") is None:
        shutil.rmtree(BASE_SAVEDIR, ignore_errors=True)
