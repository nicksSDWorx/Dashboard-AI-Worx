from __future__ import annotations

from typing import List

from .config import DIRECT_HIT_CPV_CODES, STRONG_KEYWORDS
from .models import Tender


def _direct_hit_cpv(cpv_codes: List[str]) -> bool:
    for code in cpv_codes:
        normalized = (code or "").split("-")[0].strip()
        if normalized in DIRECT_HIT_CPV_CODES:
            return True
    return False


def score(tender: Tender, cpv_hit: bool, matched_keywords: List[str]) -> int:
    unique = {kw.lower() for kw in matched_keywords}
    strong = {kw.lower() for kw in STRONG_KEYWORDS}
    n_unique = len(unique)
    n_strong = len(unique & strong)

    weighted = n_unique + n_strong

    s = 0
    if cpv_hit:
        s += 2
    if _direct_hit_cpv(tender.cpv_codes):
        s += 1
    if weighted >= 1:
        s += 1
    if weighted >= 3:
        s += 1

    title_hits = {kw.lower() for kw in matched_keywords if kw.lower() in (tender.title or "").lower()}
    if title_hits:
        s += 1

    if s <= 0:
        return 1
    return min(5, max(1, s))
