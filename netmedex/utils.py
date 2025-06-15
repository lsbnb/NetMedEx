import logging
import sys
from datetime import datetime
from uuid import uuid4


def generate_uuid():
    return str(uuid4())


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
