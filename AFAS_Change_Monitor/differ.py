"""Change detection between two sets of page snapshots.

Pure logic module - no I/O - so it's easy to unit-test.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Pattern, Sequence, Tuple

from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)


class ChangeType(str, Enum):
    NEW = "Nieuwe pagina"
    REMOVED = "Verwijderde pagina"
    TEXT_CHANGED = "Tekst gewijzigd"
    STRUCTURE_CHANGED = "Structuur gewijzigd"


@dataclass
class PageFingerprint:
    """Normalised, hashable view of a single page."""

    url: str
    text: str
    structure: str
    text_hash: str
    structure_hash: str
    fetched_at: str


@dataclass
class PageChange:
    url: str
    change_type: ChangeType
    summary: str
    before: Optional[PageFingerprint]
    after: Optional[PageFingerprint]
    # Raw (denormalised) snapshots - used by the reporter for side-by-side diffs.
    before_text: str = ""
    after_text: str = ""
    before_html: str = ""
    after_html: str = ""


@dataclass
class DiffReport:
    changes: List[PageChange] = field(default_factory=list)
    total_scanned: int = 0

    @property
    def new_pages(self) -> List[PageChange]:
        return [c for c in self.changes if c.change_type is ChangeType.NEW]

    @property
    def removed_pages(self) -> List[PageChange]:
        return [c for c in self.changes if c.change_type is ChangeType.REMOVED]

    @property
    def text_changed(self) -> List[PageChange]:
        return [c for c in self.changes if c.change_type is ChangeType.TEXT_CHANGED]

    @property
    def structure_changed(self) -> List[PageChange]:
        return [c for c in self.changes if c.change_type is ChangeType.STRUCTURE_CHANGED]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def compile_ignore_patterns(patterns: Sequence[str]) -> List[Pattern[str]]:
    compiled: List[Pattern[str]] = []
    for pat in patterns:
        try:
            compiled.append(re.compile(pat, re.IGNORECASE | re.MULTILINE))
        except re.error as exc:
            log.warning("Skipping invalid ignore pattern %r: %s", pat, exc)
    return compiled


def normalise(s: str, patterns: Sequence[Pattern[str]]) -> str:
    for pat in patterns:
        s = pat.sub("", s)
    return s


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def extract_structure(html: str) -> str:
    """Serialise the DOM without textual content.

    Captures tag name, id and classes in a canonical order so cosmetic text
    edits don't register as structural changes, but tag re-ordering, class
    changes, and new elements do.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001
        soup = BeautifulSoup(html, "html.parser")

    # Ignore elements that don't affect visible structure.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    lines: List[str] = []

    def walk(node: Tag, depth: int) -> None:
        name = node.name or ""
        if not name:
            return
        tag_id = node.get("id") or ""
        classes = node.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        classes_norm = " ".join(sorted(cls for cls in classes if cls))
        line = f"{'  ' * depth}<{name}"
        if tag_id:
            line += f" #{tag_id}"
        if classes_norm:
            line += f" .{classes_norm}"
        line += ">"
        lines.append(line)
        for child in node.children:
            if isinstance(child, Tag):
                walk(child, depth + 1)

    root = soup.find("html") or soup
    if isinstance(root, Tag):
        walk(root, 0)
    return "\n".join(lines)


def fingerprint(
    url: str,
    text: str,
    html: str,
    fetched_at: str,
    patterns: Sequence[Pattern[str]],
) -> PageFingerprint:
    norm_text = normalise(text or "", patterns)
    structure = extract_structure(html or "")
    norm_structure = normalise(structure, patterns)
    return PageFingerprint(
        url=url,
        text=norm_text,
        structure=norm_structure,
        text_hash=_hash(norm_text),
        structure_hash=_hash(norm_structure),
        fetched_at=fetched_at,
    )


# ---------------------------------------------------------------------------
# Diffing
# ---------------------------------------------------------------------------

def _line_summary(before: str, after: str, limit: int = 240) -> str:
    """Short human-readable summary of the text change."""
    import difflib

    added: List[str] = []
    removed: List[str] = []
    for line in difflib.unified_diff(
        (before or "").splitlines(),
        (after or "").splitlines(),
        lineterm="",
        n=0,
    ):
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:].strip())
    parts: List[str] = []
    if added:
        parts.append(f"+{len(added)} regel(s) toegevoegd")
    if removed:
        parts.append(f"-{len(removed)} regel(s) verwijderd")
    preview_bits: List[str] = []
    if added:
        preview_bits.append(f"+ {added[0][:80]}")
    if removed:
        preview_bits.append(f"- {removed[0][:80]}")
    text = "; ".join(parts)
    if preview_bits:
        text += " :: " + " | ".join(preview_bits)
    return (text or "geen zichtbaar verschil")[:limit]


def diff(
    previous: Dict[str, PageFingerprint],
    current: Dict[str, PageFingerprint],
    raw_current: Dict[str, Tuple[str, str]] | None = None,
    raw_previous: Dict[str, Tuple[str, str]] | None = None,
) -> DiffReport:
    """Compare two dictionaries of URL -> PageFingerprint.

    ``raw_*`` maps URL -> (text, html) for the denormalised content; used only
    to enrich :class:`PageChange` so the reporter can render full side-by-side
    views. They are optional because the differ itself works on normalised
    fingerprints.
    """
    raw_current = raw_current or {}
    raw_previous = raw_previous or {}
    changes: List[PageChange] = []

    prev_urls = set(previous.keys())
    cur_urls = set(current.keys())

    for url in sorted(cur_urls - prev_urls):
        after = current[url]
        a_text, a_html = raw_current.get(url, ("", ""))
        changes.append(
            PageChange(
                url=url,
                change_type=ChangeType.NEW,
                summary="Pagina voor het eerst gezien",
                before=None,
                after=after,
                before_text="",
                after_text=a_text,
                before_html="",
                after_html=a_html,
            )
        )

    for url in sorted(prev_urls - cur_urls):
        before = previous[url]
        b_text, b_html = raw_previous.get(url, ("", ""))
        changes.append(
            PageChange(
                url=url,
                change_type=ChangeType.REMOVED,
                summary="Pagina niet meer gevonden",
                before=before,
                after=None,
                before_text=b_text,
                after_text="",
                before_html=b_html,
                after_html="",
            )
        )

    for url in sorted(prev_urls & cur_urls):
        before = previous[url]
        after = current[url]
        text_changed = before.text_hash != after.text_hash
        structure_changed = before.structure_hash != after.structure_hash
        if not text_changed and not structure_changed:
            continue
        b_text, b_html = raw_previous.get(url, (before.text, ""))
        a_text, a_html = raw_current.get(url, (after.text, ""))
        # Text changes take priority in classification but we still record
        # structure-only changes separately when text is unchanged.
        if text_changed:
            summary = _line_summary(before.text, after.text)
            changes.append(
                PageChange(
                    url=url,
                    change_type=ChangeType.TEXT_CHANGED,
                    summary=summary,
                    before=before,
                    after=after,
                    before_text=b_text,
                    after_text=a_text,
                    before_html=b_html,
                    after_html=a_html,
                )
            )
        if structure_changed and not text_changed:
            changes.append(
                PageChange(
                    url=url,
                    change_type=ChangeType.STRUCTURE_CHANGED,
                    summary="HTML-structuur gewijzigd (tags/classes/id's)",
                    before=before,
                    after=after,
                    before_text=b_text,
                    after_text=a_text,
                    before_html=b_html,
                    after_html=a_html,
                )
            )

    return DiffReport(changes=changes, total_scanned=len(cur_urls))
