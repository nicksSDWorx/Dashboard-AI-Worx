from __future__ import annotations

import logging
import sys


def get_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("dutch_tender_scraper")
    if logger.handlers:
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        return logger

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger
