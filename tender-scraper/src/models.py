from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class Tender:
    source: str
    title: str
    authority: str = ""
    publication_date: Optional[date] = None
    deadline: Optional[date] = None
    estimated_value_eur: Optional[float] = None
    cpv_codes: List[str] = field(default_factory=list)
    scope: str = ""
    reference: str = ""
    url: str = ""
    matched_keywords: List[str] = field(default_factory=list)
    relevance_score: int = 0

    def dedupe_key(self) -> str:
        if self.reference:
            return f"ref::{self.reference.strip().lower()}"
        title = (self.title or "").strip().lower()
        authority = (self.authority or "").strip().lower()
        pub = self.publication_date.isoformat() if self.publication_date else ""
        return f"tap::{title}::{authority}::{pub}"
