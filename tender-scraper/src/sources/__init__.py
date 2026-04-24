from __future__ import annotations

import logging
from typing import List

from ..models import Tender
from . import tenderned


def fetch_all_sources(days: int, logger: logging.Logger) -> List[Tender]:
    try:
        batch = tenderned.fetch_tenderned(days, logger)
        logger.info("TenderNed: fetched %d publications", len(batch))
        return batch
    except Exception as exc:
        logger.warning("TenderNed failed: %s", exc)
        return []
