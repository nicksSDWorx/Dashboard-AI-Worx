from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import List, Optional

import feedparser

from ..config import AANBESTEDINGSKALENDER_RSS_URL, USER_AGENT
from ..models import Tender


def _entry_to_tender(entry) -> Optional[Tender]:
    title = getattr(entry, "title", "") or ""
    if not title:
        return None
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    url = getattr(entry, "link", "") or ""
    ref = getattr(entry, "id", "") or url

    pub_date: Optional[date] = None
    pub_parsed = getattr(entry, "published_parsed", None)
    if pub_parsed:
        try:
            pub_date = datetime(*pub_parsed[:6], tzinfo=timezone.utc).date()
        except (TypeError, ValueError):
            pub_date = None

    authority = getattr(entry, "author", "") or ""

    return Tender(
        source="Aanbestedingskalender",
        title=str(title),
        authority=str(authority),
        publication_date=pub_date,
        scope=str(summary)[:5000],
        reference=str(ref),
        url=str(url),
    )


def fetch_aanbestedingskalender(days: int, logger: logging.Logger) -> List[Tender]:
    try:
        feed = feedparser.parse(
            AANBESTEDINGSKALENDER_RSS_URL,
            request_headers={"User-Agent": USER_AGENT},
        )
    except Exception as exc:
        logger.debug("Aanbestedingskalender RSS unreachable: %s", exc)
        return []

    if getattr(feed, "bozo", 0) and not feed.entries:
        logger.debug("Aanbestedingskalender RSS parse failure, skipping")
        return []

    tenders: List[Tender] = []
    for entry in feed.entries:
        tender = _entry_to_tender(entry)
        if tender:
            tenders.append(tender)
    return tenders
