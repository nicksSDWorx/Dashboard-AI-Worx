from __future__ import annotations

import re
from typing import List, Tuple

from .config import CPV_CODES, KEYWORDS
from .models import Tender

_KEYWORD_PATTERNS = [
    (kw, re.compile(r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])", re.IGNORECASE))
    for kw in KEYWORDS
]

_CPV_PREFIXES = {code[:5] for code in CPV_CODES}


def _cpv_matches(cpv_codes: List[str]) -> bool:
    for code in cpv_codes:
        normalized = (code or "").split("-")[0].strip()
        if not normalized:
            continue
        if normalized in CPV_CODES or normalized[:5] in _CPV_PREFIXES and normalized in CPV_CODES:
            return True
        if normalized in CPV_CODES:
            return True
    return False


def _find_keywords(text: str) -> List[str]:
    if not text:
        return []
    hits: List[str] = []
    for kw, pattern in _KEYWORD_PATTERNS:
        if pattern.search(text):
            hits.append(kw)
    return hits


def match_tender(tender: Tender) -> Tuple[bool, List[str], bool]:
    """Return (is_match, matched_keywords, cpv_hit).

    Inclusie-regel (keuze 3d): tenders met een matchende CPV-code worden
    meegenomen; keyword-matches verhogen de score maar zijn niet vereist.

    Uitzondering: als een tender helemaal geen CPV-codes meelevert (bv.
    RSS-fallback), vallen we terug op keyword-match zodat er nog data
    overblijft. Anders zou een RSS-only run altijd 0 resultaten geven.
    """
    haystack = " ".join([tender.title or "", tender.scope or ""])
    keywords = _find_keywords(haystack)
    cpv_hit = _cpv_matches(tender.cpv_codes)
    has_no_cpv_data = not tender.cpv_codes
    include = cpv_hit or (has_no_cpv_data and bool(keywords))
    return (include, keywords, cpv_hit)


def keyword_in_title(tender: Tender) -> bool:
    return bool(_find_keywords(tender.title or ""))
