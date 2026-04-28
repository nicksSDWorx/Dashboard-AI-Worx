"""Configuration loading for AFAS Change Monitor.

The YAML file lives next to the .exe (so end-users can edit it) and falls
back to the PyInstaller _MEIPASS bundle directory when not found alongside
the executable.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

log = logging.getLogger(__name__)

CONFIG_FILENAME = "config.yaml"


@dataclass
class AppConfig:
    start_url: str = "https://www.afas.nl"
    allowed_domains: List[str] = field(default_factory=lambda: ["afas.nl", "www.afas.nl"])
    schedule_time: str = "10:00"
    schedule_day: str = "monday"
    user_agent: str = "AFAS-Change-Monitor/1.0"
    max_pages: int = 5000
    timeout_seconds: int = 30
    default_crawl_delay_seconds: float = 2.0
    max_retries: int = 3
    skip_extensions: List[str] = field(default_factory=list)
    ignore_patterns: List[str] = field(default_factory=list)


def app_base_dir() -> Path:
    """Directory containing the running executable or main.py.

    This is where ``config.yaml``, ``snapshots/``, ``reports/`` and ``logs/``
    live so users can find them next to the .exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path | None:
    """Read-only directory of PyInstaller bundled resources (if any)."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def resolve_config_path() -> Path:
    """Locate config.yaml: prefer next to the exe, fall back to the bundle."""
    external = app_base_dir() / CONFIG_FILENAME
    if external.is_file():
        return external
    bundled = _bundle_dir()
    if bundled is not None:
        inside = bundled / CONFIG_FILENAME
        if inside.is_file():
            return inside
    # Final fallback: return the external path even if missing so callers can
    # report a clear error.
    return external


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from disk, filling in defaults for missing keys."""
    cfg_path = path or resolve_config_path()
    data: dict = {}
    if cfg_path.is_file():
        try:
            with cfg_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    log.warning("config.yaml did not parse to a mapping; using defaults")
        except (OSError, yaml.YAMLError) as exc:
            log.warning("Failed to read %s: %s - using defaults", cfg_path, exc)
    else:
        log.warning("Config file not found at %s - using defaults", cfg_path)

    defaults = AppConfig()
    return AppConfig(
        start_url=str(data.get("start_url", defaults.start_url)),
        allowed_domains=list(data.get("allowed_domains", defaults.allowed_domains)),
        schedule_time=str(data.get("schedule_time", defaults.schedule_time)),
        schedule_day=str(data.get("schedule_day", defaults.schedule_day)),
        user_agent=str(data.get("user_agent", defaults.user_agent)),
        max_pages=int(data.get("max_pages", defaults.max_pages)),
        timeout_seconds=int(data.get("timeout_seconds", defaults.timeout_seconds)),
        default_crawl_delay_seconds=float(
            data.get("default_crawl_delay_seconds", defaults.default_crawl_delay_seconds)
        ),
        max_retries=int(data.get("max_retries", defaults.max_retries)),
        skip_extensions=[str(e).lower() for e in data.get("skip_extensions", [])],
        ignore_patterns=list(data.get("ignore_patterns", [])),
    )


def data_dir() -> Path:
    d = app_base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshots_dir() -> Path:
    d = app_base_dir() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reports_dir() -> Path:
    d = app_base_dir() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = app_base_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def excel_path() -> Path:
    return data_dir() / "afas_monitor_data.xlsx"


def config_path_for_opening() -> Path:
    """Path used by the 'Open config' GUI button - always the external one."""
    return app_base_dir() / CONFIG_FILENAME


def open_in_default_app(path: Path) -> None:
    """Open a file with the OS default application (best-effort)."""
    import subprocess

    path_str = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path_str)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path_str])
        else:
            subprocess.Popen(["xdg-open", path_str])
    except OSError as exc:
        log.warning("Could not open %s: %s", path, exc)
