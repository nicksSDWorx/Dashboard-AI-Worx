from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dateutil import parser as dateparse

from ..config import (
    COUNTRY_CODE_ISO3,
    CPV_CODES,
    HTTP_TIMEOUT,
    TED_DETAIL_URL_TEMPLATE,
    TED_FALLBACK_URL,
    TED_PRIMARY_URL,
    USER_AGENT,
)
from ..models import Tender

PAGE_SIZE = 100
MAX_PAGES = 20
MAX_RETRIES = 3

FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "publication-date",
    "deadline-receipt-request",
    "estimated-value",
    "classification-cpv",
    "description-lot",
    "notice-type",
    "links",
]


def _build_query(days: int, country_field: str) -> str:
    """Bouw een TED Expert Search query.

    TED v3 gebruikt de IN-operator met haakjes en spaties voor lijsten.
    Voor het land-filter proberen we zowel place-of-performance als
    buyer-country omdat niet iedere notice-type beide velden vult.
    """
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).strftime("%Y%m%d")
    cpv_list = " ".join(CPV_CODES)
    return (
        f"classification-cpv IN ({cpv_list}) "
        f"AND {country_field} IN ({COUNTRY_CODE_ISO3}) "
        f"AND publication-date>={since}"
    )


def _post_search(
    url: str,
    body: Dict[str, Any],
    session: requests.Session,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    delay = 1.0
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.post(url, json=body, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            logger.debug("TED network error on attempt %d: %s", attempt + 1, exc)
            if attempt == MAX_RETRIES:
                return None
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                logger.warning("TED returned non-JSON body: %s", exc)
                return None

        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            logger.debug("TED %s, retrying in %.1fs", resp.status_code, wait)
            if attempt == MAX_RETRIES:
                return None
            time.sleep(wait)
            delay *= 2
            continue

        if 400 <= resp.status_code < 500:
            logger.debug(
                "TED rejected query with HTTP %s: %s", resp.status_code, resp.text[:500]
            )
            return None

        logger.debug("TED unexpected HTTP %s", resp.status_code)
        return None

    return None


def _pick(obj: Any, *keys: str) -> Any:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, "", [], {}):
                return obj[key]
    return None


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for lang in ("nld", "eng", "en", "nl"):
            if lang in value and value[lang]:
                v = value[lang]
                if isinstance(v, list):
                    return " ".join(str(x) for x in v if x)
                return str(v)
        for v in value.values():
            if v:
                if isinstance(v, list):
                    return " ".join(str(x) for x in v if x)
                return str(v)
        return ""
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return " ".join(p for p in parts if p)
    return str(value)


def _parse_date(raw: Any) -> Optional[date]:
    text = _extract_text(raw)
    if not text:
        return None
    try:
        return dateparse.isoparse(text).astimezone(timezone.utc).date()
    except (ValueError, TypeError):
        try:
            return dateparse.parse(text).date()
        except (ValueError, TypeError):
            return None


def _parse_cpv(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                code = item.get("code") or item.get("value") or item.get("cpv")
                if code:
                    out.append(str(code))
        return out
    if isinstance(raw, dict):
        code = raw.get("code") or raw.get("value")
        return [str(code)] if code else []
    return []


def _parse_value(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("amount", "value", "total"):
            if key in raw:
                try:
                    return float(raw[key])
                except (TypeError, ValueError):
                    continue
    try:
        return float(str(raw))
    except (TypeError, ValueError):
        return None


def _to_tender(notice: Dict[str, Any]) -> Optional[Tender]:
    pub_number = _extract_text(_pick(notice, "publication-number", "PN"))
    title = _extract_text(_pick(notice, "notice-title", "TI"))
    if not title and not pub_number:
        return None
    authority = _extract_text(_pick(notice, "buyer-name", "AU"))
    pub_date = _parse_date(_pick(notice, "publication-date", "PD"))
    deadline = _parse_date(
        _pick(notice, "deadline-receipt-request", "deadline-date-lot", "DD", "deadline-date")
    )
    cpv = _parse_cpv(_pick(notice, "classification-cpv", "PC", "cpv"))
    scope = _extract_text(_pick(notice, "description-lot", "description", "DS"))[:5000]
    value = _parse_value(_pick(notice, "estimated-value", "VA"))

    url = ""
    links = _pick(notice, "links", "URL")
    if isinstance(links, dict):
        for key in ("html", "pdf", "xml"):
            if links.get(key):
                url = _extract_text(links[key])
                break
    if not url and pub_number:
        url = TED_DETAIL_URL_TEMPLATE.format(publication_number=pub_number)

    return Tender(
        source="TED",
        title=title or pub_number or "(untitled)",
        authority=authority,
        publication_date=pub_date,
        deadline=deadline,
        estimated_value_eur=value,
        cpv_codes=cpv,
        scope=scope,
        reference=pub_number,
        url=url,
    )


def _fetch_with_url(
    url: str,
    query: str,
    session: requests.Session,
    logger: logging.Logger,
) -> List[Tender]:
    tenders: List[Tender] = []
    iteration_token: Optional[str] = None
    for page in range(MAX_PAGES):
        body: Dict[str, Any] = {
            "query": query,
            "fields": FIELDS,
            "limit": PAGE_SIZE,
            "scope": "ACTIVE",
            "checkQuerySyntax": False,
            "paginationMode": "ITERATION",
        }
        if iteration_token:
            body["iterationNextToken"] = iteration_token
        payload = _post_search(url, body, session, logger)
        if payload is None:
            return tenders
        notices = payload.get("notices") or payload.get("results") or []
        for notice in notices:
            tender = _to_tender(notice)
            if tender:
                tenders.append(tender)
        iteration_token = (
            payload.get("iterationNextToken")
            or payload.get("nextIterationToken")
            or payload.get("iteration", {}).get("nextToken")
        )
        if not iteration_token or len(notices) < PAGE_SIZE:
            break
    return tenders


def fetch_ted(days: int, logger: logging.Logger) -> List[Tender]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    for url in (TED_PRIMARY_URL, TED_FALLBACK_URL):
        for country_field in ("place-of-performance", "buyer-country"):
            query = _build_query(days, country_field)
            logger.debug("TED attempt url=%s country-field=%s", url, country_field)
            tenders = _fetch_with_url(url, query, session, logger)
            if tenders:
                return tenders
    return []
