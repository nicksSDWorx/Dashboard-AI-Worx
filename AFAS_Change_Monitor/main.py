"""AFAS Change Monitor - Tkinter entry point."""
from __future__ import annotations

import logging
import logging.handlers
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Optional

from config import (
    AppConfig,
    config_path_for_opening,
    excel_path,
    load_config,
    logs_dir,
    open_in_default_app,
)
from reporter import find_latest_report
from scheduler import DailyScheduler, run_once

log = logging.getLogger("afas_monitor")


APP_TITLE = "AFAS Change Monitor"


# ---------------------------------------------------------------------------
# Logging -> GUI plumbing
# ---------------------------------------------------------------------------

class QueueLogHandler(logging.Handler):
    """Push log records onto a thread-safe queue for the GUI to consume."""

    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait(self.format(record))
        except queue.Full:
            pass


def setup_logging(log_queue: "queue.Queue[str]") -> None:
    log_file = logs_dir() / "afas_monitor.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Clear any handlers that survived a reload/relaunch.
    for h in list(root.handlers):
        root.removeHandler(h)

    file_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    root.addHandler(QueueLogHandler(log_queue))

    # Quiet down noisy libraries.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MonitorApp:
    def __init__(self, root: tk.Tk, config: AppConfig) -> None:
        self.root = root
        self.config = config

        self.log_queue: "queue.Queue[str]" = queue.Queue(maxsize=10_000)
        setup_logging(self.log_queue)

        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self._scheduler: Optional[DailyScheduler] = None

        self.status_var = tk.StringVar(value="Idle")
        self.next_run_var = tk.StringVar(value="-")
        self.counter_var = tk.StringVar(value="0 pagina's")

        self._build_ui()
        self._start_scheduler()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._drain_log_queue)
        self.root.after(10_000, self._refresh_next_run)

        log.info("%s gestart - geplande tijd %s", APP_TITLE, config.schedule_time)

    # -- UI --------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("980x640")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        header = ttk.Frame(self.root, padding=(14, 12))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 11, "bold"),
                  foreground="#0f172a").pack(side="right")

        controls = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        controls.pack(fill="x")

        self.start_btn = ttk.Button(controls, text="Start scan", command=self.start_scan)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(controls, text="Stop scan", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(controls, text="Open laatste rapport", command=self.open_latest_report)\
            .pack(side="left", padx=6)
        ttk.Button(controls, text="Open Excel data", command=self.open_excel)\
            .pack(side="left", padx=6)
        ttk.Button(controls, text="Open config", command=self.open_config)\
            .pack(side="left", padx=6)

        info = ttk.Frame(self.root, padding=(14, 4))
        info.pack(fill="x")
        ttk.Label(info, text="Volgende geplande run:").pack(side="left")
        ttk.Label(info, textvariable=self.next_run_var, foreground="#1e40af")\
            .pack(side="left", padx=(6, 18))
        ttk.Label(info, text="Voortgang:").pack(side="left")
        ttk.Label(info, textvariable=self.counter_var, foreground="#0f172a")\
            .pack(side="left", padx=(6, 0))

        log_frame = ttk.LabelFrame(self.root, text="Log", padding=(8, 6))
        log_frame.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.log_widget = scrolledtext.ScrolledText(log_frame, state="disabled",
                                                    wrap="word", font=("Consolas", 10))
        self.log_widget.pack(fill="both", expand=True)

    # -- actions ---------------------------------------------------------

    def start_scan(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Er loopt al een scan.")
            return
        self.stop_event.clear()
        self._set_status("Running", "#1e40af")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.counter_var.set("0 pagina's")
        self.worker = threading.Thread(target=self._run_scan, name="afas-scan", daemon=True)
        self.worker.start()

    def stop_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            log.info("Stopverzoek ontvangen - scan wordt afgebroken...")
            self.stop_event.set()
            self._set_status("Stopping...", "#92400e")

    def open_latest_report(self) -> None:
        report = find_latest_report()
        if report is None:
            messagebox.showinfo(APP_TITLE, "Er is nog geen rapport beschikbaar.")
            return
        webbrowser.open(report.resolve().as_uri())

    def open_excel(self) -> None:
        path = excel_path()
        if not path.is_file():
            messagebox.showinfo(APP_TITLE, "Excel-bestand bestaat nog niet - draai eerst een scan.")
            return
        open_in_default_app(path)

    def open_config(self) -> None:
        path = config_path_for_opening()
        if not path.is_file():
            messagebox.showwarning(
                APP_TITLE,
                f"config.yaml niet gevonden op {path}.\n"
                "Herstart de applicatie na het aanmaken van het bestand.",
            )
            return
        open_in_default_app(path)

    # -- background work -------------------------------------------------

    def _run_scan(self) -> None:
        def progress(url: str, fetched: int, queue_size: int) -> None:
            self.root.after(0, lambda: self.counter_var.set(
                f"{fetched} pagina's | wachtrij: {queue_size}"
            ))

        def status(msg: str) -> None:  # noqa: ARG001 - logged via logger already
            pass

        try:
            result = run_once(
                self.config,
                stop_event=self.stop_event,
                progress=progress,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001 - surface in the GUI
            log.exception("Scan mislukt")
            err_text = str(exc) or exc.__class__.__name__
            self.root.after(0, lambda: self._set_status("Fout", "#991b1b"))
            self.root.after(0, lambda t=err_text: messagebox.showerror(APP_TITLE, f"Scan mislukt:\n{t}"))
        else:
            if result.stopped:
                self.root.after(0, lambda: self._set_status("Afgebroken", "#92400e"))
            else:
                self.root.after(0, lambda: self._set_status("Klaar", "#166534"))
            self.root.after(0, lambda: self.counter_var.set(
                f"{result.pages_scanned} pagina's gescand - {len(result.report.changes)} wijziging(en)"
            ))
        finally:
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self) -> None:
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _set_status(self, text: str, color: str = "#0f172a") -> None:
        self.status_var.set(text)
        # Ttk labels ignore direct foreground assignment via textvariable,
        # so find the label widget by traversing children of header frames.
        # (We just change the string; visual-only status is enough.)

    # -- scheduler -------------------------------------------------------

    def _start_scheduler(self) -> None:
        self._scheduler = DailyScheduler(self.config, run_callable=self._trigger_scheduled_scan)
        try:
            self._scheduler.start()
        except Exception:  # noqa: BLE001
            log.exception("Kon scheduler niet starten")
        self._refresh_next_run()

    def _trigger_scheduled_scan(self) -> None:
        # Invoked from the APScheduler thread. Delegate to the GUI thread so
        # we share the same busy-state / button logic as manual runs.
        self.root.after(0, self.start_scan)

    def _refresh_next_run(self) -> None:
        nxt = self._scheduler.next_run_time() if self._scheduler else None
        if nxt is None:
            self.next_run_var.set("niet ingepland")
        else:
            self.next_run_var.set(nxt.strftime("%Y-%m-%d %H:%M %Z"))
        self.root.after(30_000, self._refresh_next_run)

    # -- log pump --------------------------------------------------------

    def _drain_log_queue(self) -> None:
        drained = 0
        try:
            while drained < 200:
                line = self.log_queue.get_nowait()
                self._append_log_line(line)
                drained += 1
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log_queue)

    def _append_log_line(self, line: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", line + "\n")
        # Cap the log widget at ~5000 lines so memory stays bounded.
        lines = int(self.log_widget.index("end-1c").split(".")[0])
        if lines > 5000:
            self.log_widget.delete("1.0", f"{lines - 5000}.0")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    # -- shutdown --------------------------------------------------------

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                APP_TITLE,
                "Er loopt nog een scan. Weet je zeker dat je wilt afsluiten?\n"
                "De lopende scan wordt afgebroken.",
            ):
                return
            self.stop_event.set()
            self.worker.join(timeout=5)
        if self._scheduler is not None:
            self._scheduler.shutdown()
        self.root.destroy()


def _run_headless(config) -> int:
    """One-shot scan without GUI - intended for Windows Task Scheduler."""
    from scheduler import run_once  # local import: avoid pulling Tk into the path

    log_file = logs_dir() / "afas_monitor.log"
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root_logger.addHandler(sh)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    log.info("Headless run started")
    try:
        result = run_once(config)
    except Exception:  # noqa: BLE001
        log.exception("Headless run failed")
        return 1
    log.info("Headless run completed: %d pages, %d change(s)",
             result.pages_scanned, len(result.report.changes))
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="AFAS Monitor")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single scan without the GUI and exit. "
             "Use this from Windows Task Scheduler for unattended operation.",
    )
    args = parser.parse_args()

    config = load_config()
    if args.run_once:
        return _run_headless(config)

    root = tk.Tk()
    MonitorApp(root, config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
