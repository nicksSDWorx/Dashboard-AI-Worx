from __future__ import annotations

from typing import Dict, List

from .models import Tender


def dedupe(tenders: List[Tender]) -> List[Tender]:
    grouped: Dict[str, Tender] = {}
    for tender in tenders:
        key = tender.dedupe_key()
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = tender
            continue

        sources = sorted({s.strip() for s in existing.source.split("+")} | {tender.source})
        existing.source = " + ".join(sources)

        if not existing.scope and tender.scope:
            existing.scope = tender.scope
        if not existing.authority and tender.authority:
            existing.authority = tender.authority
        if existing.estimated_value_eur is None and tender.estimated_value_eur is not None:
            existing.estimated_value_eur = tender.estimated_value_eur
        if not existing.deadline and tender.deadline:
            existing.deadline = tender.deadline
        if not existing.cpv_codes and tender.cpv_codes:
            existing.cpv_codes = tender.cpv_codes
        merged_keywords = sorted(set(existing.matched_keywords) | set(tender.matched_keywords))
        existing.matched_keywords = merged_keywords
        existing.relevance_score = max(existing.relevance_score, tender.relevance_score)

    return list(grouped.values())
