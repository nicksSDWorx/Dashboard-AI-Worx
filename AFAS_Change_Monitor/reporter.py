"""Side-by-side HTML report generator.

Uses :class:`difflib.HtmlDiff` for the per-page text and structure diffs and
wraps them in a custom shell with a run summary.
"""
from __future__ import annotations

import difflib
import html
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import reports_dir
from differ import ChangeType, DiffReport, PageChange, extract_structure

log = logging.getLogger(__name__)


_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       margin: 0; padding: 0; background: #f4f6fa; color: #1d1d1f; }
header { background: #0f172a; color: #fff; padding: 24px 32px; }
header h1 { margin: 0 0 8px 0; font-size: 22px; }
header .meta { color: #cbd5e1; font-size: 13px; }
.summary { display: flex; flex-wrap: wrap; gap: 16px; padding: 24px 32px; background: #fff;
           border-bottom: 1px solid #e2e8f0; }
.summary .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
                 padding: 12px 18px; min-width: 160px; }
.summary .card .label { font-size: 12px; color: #64748b; text-transform: uppercase;
                        letter-spacing: 0.04em; }
.summary .card .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
main { padding: 24px 32px 48px; }
.change { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
          margin-bottom: 24px; overflow: hidden; }
.change h2 { margin: 0; padding: 14px 18px; font-size: 15px; font-weight: 600;
             background: #f1f5f9; border-bottom: 1px solid #e2e8f0; }
.change .url { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
               font-size: 12px; color: #0369a1; word-break: break-all; }
.change .badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
                 font-size: 11px; font-weight: 600; margin-left: 8px; vertical-align: middle; }
.badge-new       { background: #dcfce7; color: #166534; }
.badge-removed   { background: #fee2e2; color: #991b1b; }
.badge-text      { background: #dbeafe; color: #1e40af; }
.badge-structure { background: #fef3c7; color: #92400e; }
.change-body { padding: 18px; }
.change .summary-text { color: #334155; font-size: 13px; margin: 0 0 12px; }
details { margin-top: 14px; }
details > summary { cursor: pointer; font-weight: 600; color: #0f172a; padding: 6px 0; }
table.diff { width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
             font-size: 12px; border-collapse: collapse; }
table.diff th { background: #0f172a; color: #fff; padding: 6px; }
table.diff td { padding: 2px 6px; vertical-align: top; white-space: pre-wrap;
                word-break: break-word; }
.diff_header { background: #f1f5f9; color: #64748b; }
.diff_next   { background: #f1f5f9; }
.diff_add    { background: #dcfce7; }
.diff_chg    { background: #fef3c7; }
.diff_sub    { background: #fee2e2; }
.empty { padding: 48px; text-align: center; color: #64748b; background: #fff;
         border: 1px dashed #cbd5e1; border-radius: 10px; }
.legend { font-size: 12px; color: #475569; margin-top: 8px; }
"""


_BADGE_CLASS = {
    ChangeType.NEW: "badge-new",
    ChangeType.REMOVED: "badge-removed",
    ChangeType.TEXT_CHANGED: "badge-text",
    ChangeType.STRUCTURE_CHANGED: "badge-structure",
}


@dataclass
class ReportMeta:
    total_scanned: int
    started_at: str
    finished_at: str


def _safe(text: str) -> str:
    return html.escape(text or "")


def _build_table(before: str, after: str, from_label: str, to_label: str) -> str:
    differ = difflib.HtmlDiff(wrapcolumn=100)
    before_lines = (before or "").splitlines() or [""]
    after_lines = (after or "").splitlines() or [""]
    try:
        table = differ.make_table(
            before_lines,
            after_lines,
            fromdesc=from_label,
            todesc=to_label,
            context=True,
            numlines=3,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("HtmlDiff failed (%s) - falling back to plain pre block", exc)
        return (
            "<pre>" + _safe("\n".join(
                difflib.unified_diff(before_lines, after_lines,
                                     fromfile=from_label, tofile=to_label, lineterm="")
            )) + "</pre>"
        )
    # HtmlDiff injects its own <style>; strip it - we have our own CSS.
    style_start = table.find("<style")
    if style_start != -1:
        style_end = table.find("</style>", style_start)
        if style_end != -1:
            table = table[:style_start] + table[style_end + len("</style>"):]
    return table


def _render_change(change: PageChange) -> str:
    badge = _BADGE_CLASS.get(change.change_type, "")
    url_safe = _safe(change.url)
    title = (
        f'<h2>{_safe(change.change_type.value)}'
        f'<span class="badge {badge}">{_safe(change.change_type.value)}</span></h2>'
    )
    parts = [f'<section class="change">{title}<div class="change-body">']
    parts.append(f'<div class="url">{url_safe}</div>')
    parts.append(f'<p class="summary-text">{_safe(change.summary)}</p>')

    if change.change_type is ChangeType.NEW:
        parts.append('<details open><summary>Volledige tekst (nieuw)</summary>')
        parts.append(f'<pre>{_safe(change.after_text)}</pre></details>')
    elif change.change_type is ChangeType.REMOVED:
        parts.append('<details><summary>Laatst bekende tekst</summary>')
        parts.append(f'<pre>{_safe(change.before_text)}</pre></details>')
    else:
        if change.before_text != change.after_text:
            parts.append('<details open><summary>Tekst diff (zichtbare tekst)</summary>')
            parts.append(_build_table(change.before_text, change.after_text, "Vorige", "Nieuwe"))
            parts.append('</details>')
        before_struct = extract_structure(change.before_html) if change.before_html else ""
        after_struct = extract_structure(change.after_html) if change.after_html else ""
        if before_struct != after_struct:
            parts.append('<details><summary>HTML-structuur diff (tags/classes/id\'s)</summary>')
            parts.append(_build_table(before_struct, after_struct, "Vorige structuur", "Nieuwe structuur"))
            parts.append('</details>')

    parts.append('</div></section>')
    return "".join(parts)


def render_report(report: DiffReport, meta: ReportMeta) -> str:
    changes_html: List[str] = []
    if not report.changes:
        changes_html.append(
            '<div class="empty">Geen wijzigingen gedetecteerd tijdens deze run.</div>'
        )
    else:
        order = {
            ChangeType.NEW: 0,
            ChangeType.REMOVED: 1,
            ChangeType.TEXT_CHANGED: 2,
            ChangeType.STRUCTURE_CHANGED: 3,
        }
        for change in sorted(report.changes, key=lambda c: (order.get(c.change_type, 9), c.url)):
            changes_html.append(_render_change(change))

    cards = [
        ("Gescand", report.total_scanned or meta.total_scanned),
        ("Nieuw", len(report.new_pages)),
        ("Verwijderd", len(report.removed_pages)),
        ("Tekst gewijzigd", len(report.text_changed)),
        ("Structuur gewijzigd", len(report.structure_changed)),
        ("Totaal wijzigingen", len(report.changes)),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{_safe(label)}</div>'
        f'<div class="value">{value}</div></div>'
        for label, value in cards
    )

    return f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8">
<title>AFAS Change Monitor - {_safe(meta.finished_at[:10])}</title>
<style>{_CSS}</style>
</head><body>
<header>
  <h1>AFAS Change Monitor - rapport {_safe(meta.finished_at[:10])}</h1>
  <div class="meta">Scan gestart {_safe(meta.started_at)} UTC, voltooid {_safe(meta.finished_at)} UTC</div>
</header>
<section class="summary">{cards_html}</section>
<main>
  <p class="legend">Groen = toegevoegd, rood = verwijderd, geel = gewijzigd.</p>
  {''.join(changes_html)}
</main>
</body></html>
"""


def write_report(
    report: DiffReport,
    meta: ReportMeta,
    output_dir: Optional[Path] = None,
    date_str: Optional[str] = None,
) -> Path:
    out_dir = output_dir or reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = date_str or datetime.utcnow().strftime("%Y-%m-%d")
    out_path = out_dir / f"report_{date_str}.html"
    # If a report for today already exists, suffix with time so we don't overwrite.
    if out_path.exists():
        suffix = datetime.utcnow().strftime("%H%M%S")
        out_path = out_dir / f"report_{date_str}_{suffix}.html"
    out_path.write_text(render_report(report, meta), encoding="utf-8")
    log.info("Report written to %s", out_path)
    return out_path


def find_latest_report(output_dir: Optional[Path] = None) -> Optional[Path]:
    out_dir = output_dir or reports_dir()
    if not out_dir.is_dir():
        return None
    reports = sorted(out_dir.glob("report_*.html"))
    return reports[-1] if reports else None
