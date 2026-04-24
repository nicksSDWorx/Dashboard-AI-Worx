"""Scheduler + orchestration.

Exposes two public entry points:

* :func:`run_once` - performs a full crawl -> diff -> persist -> report cycle,
  safe to call from either the GUI or the scheduler.
* :class:`DailyScheduler` - wraps APScheduler's BackgroundScheduler to run
  :func:`run_once` at the configured time every day.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from differ import DiffReport, compile_ignore_patterns, diff, fingerprint
from reporter import ReportMeta, write_report
from scraper import Scraper
from storage import Storage

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]
StatusCallback = Callable[[str], None]


class RunResult:
    def __init__(
        self,
        report: DiffReport,
        report_path: Optional[Path],
        pages_scanned: int,
        started_at: str,
        finished_at: str,
        stopped: bool = False,
    ) -> None:
        self.report = report
        self.report_path = report_path
        self.pages_scanned = pages_scanned
        self.started_at = started_at
        self.finished_at = finished_at
        self.stopped = stopped


def run_once(
    config: AppConfig,
    stop_event: Optional[threading.Event] = None,
    progress: Optional[ProgressCallback] = None,
    status: Optional[StatusCallback] = None,
    storage: Optional[Storage] = None,
) -> RunResult:
    """Execute a single scan end-to-end."""
    stop_event = stop_event or threading.Event()
    storage = storage or Storage()

    def _status(msg: str) -> None:
        log.info(msg)
        if status is not None:
            try:
                status(msg)
            except Exception:  # noqa: BLE001
                log.exception("Status callback raised - ignoring")

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _status("Vorige snapshots laden...")
    previous_pages = storage.load_pages_index()
    previous_fps, previous_raw = storage.load_previous_fingerprints(previous_pages)
    _status(f"{len(previous_pages)} bekende pagina(s) geladen.")

    _status("Crawl starten...")
    scraper = Scraper(config=config, stop_event=stop_event, progress=progress)
    snapshots = scraper.crawl()
    _status(f"Crawl klaar - {len(snapshots)} pagina(s) opgehaald.")

    patterns = compile_ignore_patterns(config.ignore_patterns)

    current_fps = {}
    current_raw = {}
    for snap in snapshots:
        if snap.error in {"stopped", "non-html"}:
            continue
        if not snap.html and not snap.text:
            # Network error - don't treat as "seen" so we don't mark as REMOVED next run.
            continue
        fp = fingerprint(snap.url, snap.text, snap.html, snap.fetched_at, patterns)
        current_fps[snap.url] = fp
        current_raw[snap.url] = (snap.text, snap.html)

    _status("Verschillen detecteren...")
    report = diff(previous_fps, current_fps, raw_current=current_raw, raw_previous=previous_raw)
    report.total_scanned = len(current_fps)
    _status(
        f"Wijzigingen: {len(report.new_pages)} nieuw, "
        f"{len(report.removed_pages)} verwijderd, "
        f"{len(report.text_changed)} tekst, "
        f"{len(report.structure_changed)} structuur."
    )

    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = ReportMeta(
        total_scanned=report.total_scanned,
        started_at=started_at,
        finished_at=finished_at,
    )
    _status("Rapport schrijven...")
    report_path = write_report(report, meta)

    _status("Opslaan naar Excel...")
    storage.persist_run(snapshots, current_fps, report, report_file=report_path)

    stopped = stop_event.is_set()
    _status("Scan afgebroken." if stopped else "Scan voltooid.")
    return RunResult(
        report=report,
        report_path=report_path,
        pages_scanned=len(current_fps),
        started_at=started_at,
        finished_at=finished_at,
        stopped=stopped,
    )


class DailyScheduler:
    """BackgroundScheduler wrapper that runs :func:`run_once` daily."""

    def __init__(
        self,
        config: AppConfig,
        run_callable: Callable[[], None],
    ) -> None:
        self.config = config
        self.run_callable = run_callable
        self._scheduler = BackgroundScheduler(timezone="Europe/Amsterdam")
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        hour, minute = _parse_hhmm(self.config.schedule_time)
        self._scheduler.add_job(
            self._safe_run,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="daily_scan",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        self._started = True
        log.info("Daily scan scheduled at %02d:%02d Europe/Amsterdam", hour, minute)

    def shutdown(self) -> None:
        if self._started:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                log.exception("Error shutting scheduler down")
            self._started = False

    def next_run_time(self) -> Optional[datetime]:
        job = self._scheduler.get_job("daily_scan") if self._started else None
        return job.next_run_time if job else None

    def _safe_run(self) -> None:
        try:
            self.run_callable()
        except Exception:  # noqa: BLE001 - never let the scheduler die
            log.exception("Scheduled run failed")


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hh, mm = value.strip().split(":", 1)
        hour, minute = int(hh), int(mm)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return hour, minute
    except (ValueError, AttributeError) as exc:
        log.warning("Invalid schedule_time %r, defaulting to 03:00 (%s)", value, exc)
        return 3, 0
