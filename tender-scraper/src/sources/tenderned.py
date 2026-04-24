from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser
import requests
from dateutil import parser as dateparse

from ..config import (
    HTTP_TIMEOUT,
    TENDERNED_DETAIL_URL_TEMPLATE,
    TENDERNED_PAPI_URL,
    TENDERNED_RSS_URL,
    USER_AGENT,
)
from ..models import Tender

PAGE_SIZE = 100
MAX_PAGES = 20


def _parse_iso_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return dateparse.isoparse(str(value)).astimezone(timezone.utc).date()
    except (ValueError, TypeError):
        try:
            return dateparse.parse(str(value)).date()
        except (ValueError, TypeError):
            return None


def _extract_cpv(record: Dict[str, Any]) -> List[str]:
    cpv_field = (
        record.get("cpvCodes")
        or record.get("cpvs")
        or record.get("cpv")
        or []
    )
    out: List[str] = []
    if isinstance(cpv_field, list):
        for item in cpv_field:
            if isinstance(item, dict):
                code = item.get("code") or item.get("value")
                if code:
                    out.append(str(code))
            elif isinstance(item, str):
                out.append(item)
    return out


def _papi_to_tender(record: Dict[str, Any]) -> Optional[Tender]:
    title = (
        record.get("opdrachtOmschrijving")
        or record.get("titel")
        or record.get("title")
        or ""
    )
    authority = (
        record.get("aanbestedendeDienstNaam")
        or record.get("aanbestedendeDienst", {}).get("naam")
        if isinstance(record.get("aanbestedendeDienst"), dict)
        else record.get("aanbestedendeDienstNaam") or ""
    ) or ""
    ref = (
        record.get("publicatieId")
        or record.get("aankondigingId")
        or record.get("id")
        or ""
    )
    pub_date = _parse_iso_date(record.get("publicatieDatum") or record.get("datumPublicatie"))
    deadline = _parse_iso_date(
        record.get("sluitingsDatum")
        or record.get("inschrijvingsTermijn")
        or record.get("deadline")
    )
    cpv_codes = _extract_cpv(record)
    scope = (record.get("omschrijving") or record.get("scope") or "")[:5000]

    url = record.get("url") or ""
    if not url and ref:
        url = TENDERNED_DETAIL_URL_TEMPLATE.format(publicatie_id=ref)

    if not title and not scope:
        return None

    return Tender(
        source="TenderNed",
        title=str(title),
        authority=str(authority) if authority else "",
        publication_date=pub_date,
        deadline=deadline,
        cpv_codes=cpv_codes,
        scope=str(scope),
        reference=str(ref),
        url=url,
    )


def _fetch_papi(days: int, logger: logging.Logger) -> List[Tender]:
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    tenders: List[Tender] = []
    for page in range(MAX_PAGES):
        params = {
            "publicatieDatumVanaf": since,
            "publicatieType": "AANKONDIGING_VAN_EEN_OPDRACHT",
            "pageSize": PAGE_SIZE,
            "page": page,
        }
        try:
            resp = session.get(TENDERNED_PAPI_URL, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            logger.debug("TenderNed papi network error: %s", exc)
            raise
        if resp.status_code != 200:
            logger.debug(
                "TenderNed papi HTTP %s: %s", resp.status_code, resp.text[:300]
            )
            raise RuntimeError(f"papi HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"papi non-JSON: {exc}") from exc

        records = (
            payload.get("content")
            or payload.get("publicaties")
            or payload.get("items")
            or []
        )
        if not records:
            break
        for record in records:
            tender = _papi_to_tender(record)
            if tender:
                tenders.append(tender)
        if len(records) < PAGE_SIZE:
            break
    return tenders


def _rss_to_tender(entry: Any) -> Optional[Tender]:
    title = getattr(entry, "title", "") or ""
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

    if not title:
        return None

    authority = getattr(entry, "author", "") or ""

    return Tender(
        source="TenderNed",
        title=str(title),
        authority=str(authority),
        publication_date=pub_date,
        scope=str(summary)[:5000],
        reference=str(ref),
        url=str(url),
    )


def _fetch_rss(logger: logging.Logger) -> List[Tender]:
    feed = feedparser.parse(
        TENDERNED_RSS_URL,
        request_headers={"User-Agent": USER_AGENT},
    )
    if getattr(feed, "bozo", 0) and not feed.entries:
        raise RuntimeError(f"RSS parse failure: {getattr(feed, 'bozo_exception', 'unknown')}")
    tenders: List[Tender] = []
    for entry in feed.entries:
        tender = _rss_to_tender(entry)
        if tender:
            tenders.append(tender)
    return tenders


def fetch_tenderned(days: int, logger: logging.Logger) -> List[Tender]:
    try:
        tenders = _fetch_papi(days, logger)
        if tenders:
            return tenders
        logger.debug("TenderNed papi returned 0 publications, falling back to RSS")
    except Exception as exc:
        logger.debug("TenderNed papi unavailable (%s), falling back to RSS", exc)

    try:
        return _fetch_rss(logger)
    except Exception as exc:
        logger.warning("TenderNed RSS fallback failed: %s", exc)
        return []
