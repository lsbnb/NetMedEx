import logging


def config_logger(is_debug):
    if is_debug:
        logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S",
                            level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s",
                            level=logging.INFO)
