from __future__ import annotations

import logging
import sys
from datetime import datetime
from uuid import uuid4


def generate_uuid():
    return str(uuid4())


def generate_stable_id(input_str: str):
    import hashlib

    return hashlib.sha1(input_str.encode("utf-8")).hexdigest()


def config_logger(is_debug: bool, filename: str | None = None):
    handlers = [logging.StreamHandler(stream=sys.stdout)]

    if filename is not None:
        now = datetime.now().strftime("%y%m%d%H%M%S")
        logfile = f"{filename}_{now}.log"
        handlers.append(logging.FileHandler(logfile, mode="w"))

    if is_debug:
        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.DEBUG,
            handlers=handlers,
        )
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO, handlers=handlers)


def is_notebook():
    try:
        shell = get_ipython().__class__.__name__  # type: ignore
        return shell == "ZMQInteractiveShell"
    except NameError:
        return False


def detect_query_language(text: str) -> str:
    """
    Detect the primary language of a query string using Unicode character ranges.
    Returns a human-readable language name suitable for use in LLM prompts.
    """
    if not text:
        return "English"
    # Japanese: Hiragana (U+3040-U+309F) or Katakana (U+30A0-U+30FF)
    if any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" for c in text):
        return "Japanese"
    # Korean: Hangul (U+AC00-U+D7AF)
    if any("\uac00" <= c <= "\ud7af" for c in text):
        return "Korean"
    # CJK Unified Ideographs — Chinese
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "Traditional Chinese"
    return "English"
