from __future__ import annotations

import logging
from typing import List

from ..models import Tender
from . import aanbestedingskalender, ted, tenderned


def fetch_all_sources(days: int, logger: logging.Logger) -> List[Tender]:
    results: List[Tender] = []
    for name, fetch in (
        ("TED", ted.fetch_ted),
        ("TenderNed", tenderned.fetch_tenderned),
        ("Aanbestedingskalender", aanbestedingskalender.fetch_aanbestedingskalender),
    ):
        try:
            batch = fetch(days, logger)
            logger.info("%s: fetched %d publications", name, len(batch))
            results.extend(batch)
        except Exception as exc:
            logger.warning("%s failed: %s", name, exc)
    return results
