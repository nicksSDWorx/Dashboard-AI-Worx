"""Crawler for AFAS Change Monitor.

Recursively fetches all internal HTML pages, respecting robots.txt and
Crawl-delay. Returns a list of :class:`PageSnapshot` objects that downstream
modules (differ, storage) consume.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from config import AppConfig

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]
"""progress(url, fetched_count, queue_size) -> None"""

_NON_VISIBLE_TAGS = {"script", "style", "noscript", "template", "iframe"}


@dataclass
class PageSnapshot:
    """One fetched page at one point in time."""

    url: str
    status: int
    html: str
    text: str
    content_type: str
    fetched_at: str  # ISO-8601 UTC
    error: Optional[str] = None
    links_found: List[str] = field(default_factory=list)


def _canonicalize(url: str) -> str:
    """Normalise a URL so that trivially different spellings don't create dupes."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    # Lowercase the scheme and host, strip default ports, collapse empty paths.
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.hostname or ""
    if parsed.port and not (
        (scheme == "http" and parsed.port == 80)
        or (scheme == "https" and parsed.port == 443)
    ):
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or "/"
    # Drop trailing slash except for the root so /foo and /foo/ match.
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = parsed.query
    return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "")


def _domain_allowed(url: str, allowed: Iterable[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in (a.lower() for a in allowed))


def _has_skipped_extension(url: str, skip_extensions: Iterable[str]) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in skip_extensions)


def _extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(_NON_VISIBLE_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse whitespace line by line to keep diffs stable.
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _looks_like_html(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return "html" in ct or "xml" in ct or ct == ""


class RobotsPolicy:
    """Small wrapper around :class:`urllib.robotparser.RobotFileParser`.

    Caches per-host parsers so we fetch /robots.txt at most once per host
    per crawl.
    """

    def __init__(self, user_agent: str, fallback_delay: float) -> None:
        self._user_agent = user_agent
        self._fallback_delay = fallback_delay
        self._parsers: dict[str, RobotFileParser] = {}

    def _parser_for(self, url: str) -> RobotFileParser:
        host = urlparse(url).netloc
        parser = self._parsers.get(host)
        if parser is not None:
            return parser
        parser = RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        try:
            parser.set_url(robots_url)
            parser.read()
            log.info("Loaded robots.txt from %s", robots_url)
        except Exception as exc:  # noqa: BLE001 - robotparser can raise several
            log.warning("Could not read %s: %s (allowing all)", robots_url, exc)
            # Empty parser => allow all by default.
        self._parsers[host] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        try:
            return self._parser_for(url).can_fetch(self._user_agent, url)
        except Exception:  # noqa: BLE001
            return True

    def crawl_delay(self, url: str) -> float:
        parser = self._parser_for(url)
        try:
            delay = parser.crawl_delay(self._user_agent)
        except Exception:  # noqa: BLE001
            delay = None
        return float(delay) if delay else self._fallback_delay


class Scraper:
    """BFS crawler with robots.txt compliance and retries."""

    def __init__(
        self,
        config: AppConfig,
        stop_event: Optional[threading.Event] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> None:
        self.config = config
        self.stop_event = stop_event or threading.Event()
        self.progress = progress
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "nl,en;q=0.8",
            }
        )
        self.robots = RobotsPolicy(config.user_agent, config.default_crawl_delay_seconds)

    # -- public API -------------------------------------------------------

    def crawl(self) -> List[PageSnapshot]:
        """Run the full crawl and return all fetched page snapshots."""
        start = _canonicalize(self.config.start_url)
        if not _domain_allowed(start, self.config.allowed_domains):
            raise ValueError(
                f"start_url {start!r} is not within allowed_domains {self.config.allowed_domains!r}"
            )

        queue: deque[str] = deque([start])
        seen: Set[str] = {start}
        results: List[PageSnapshot] = []
        last_fetch_per_host: dict[str, float] = {}

        while queue:
            if self.stop_event.is_set():
                log.info("Stop requested - aborting crawl with %d pages fetched", len(results))
                break
            if len(results) >= self.config.max_pages:
                log.warning("Reached max_pages=%d - stopping crawl", self.config.max_pages)
                break

            url = queue.popleft()

            if not self.robots.can_fetch(url):
                log.info("robots.txt disallows %s", url)
                continue

            host = urlparse(url).netloc
            delay = self.robots.crawl_delay(url)
            last = last_fetch_per_host.get(host, 0.0)
            wait = (last + delay) - time.monotonic()
            if wait > 0:
                # Sleep in small chunks so a stop request is picked up promptly.
                self._interruptible_sleep(wait)
                if self.stop_event.is_set():
                    break

            snapshot = self._fetch(url)
            last_fetch_per_host[host] = time.monotonic()
            results.append(snapshot)

            if self.progress is not None:
                try:
                    self.progress(url, len(results), len(queue))
                except Exception:  # noqa: BLE001 - never let UI kill the crawl
                    log.exception("Progress callback raised - ignoring")

            for link in snapshot.links_found:
                canon = _canonicalize(link)
                if canon in seen:
                    continue
                if not _domain_allowed(canon, self.config.allowed_domains):
                    continue
                if _has_skipped_extension(canon, self.config.skip_extensions):
                    continue
                seen.add(canon)
                queue.append(canon)

        return results

    # -- internals --------------------------------------------------------

    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if self.stop_event.wait(min(0.5, remaining)):
                return

    def _fetch(self, url: str) -> PageSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self.config.max_retries + 1):
            if self.stop_event.is_set():
                return PageSnapshot(
                    url=url, status=0, html="", text="", content_type="",
                    fetched_at=now, error="stopped",
                )
            try:
                resp = self.session.get(
                    url, timeout=self.config.timeout_seconds, allow_redirects=True
                )
                content_type = resp.headers.get("Content-Type", "")
                if resp.status_code >= 400:
                    log.warning("HTTP %s on %s (attempt %d)", resp.status_code, url, attempt)
                    if 500 <= resp.status_code < 600 and attempt < self.config.max_retries:
                        self._interruptible_sleep(1.5 * attempt)
                        continue
                    return PageSnapshot(
                        url=url, status=resp.status_code, html="", text="",
                        content_type=content_type, fetched_at=now,
                        error=f"HTTP {resp.status_code}",
                    )
                if not _looks_like_html(content_type):
                    log.debug("Skipping non-HTML content at %s (%s)", url, content_type)
                    return PageSnapshot(
                        url=url, status=resp.status_code, html="", text="",
                        content_type=content_type, fetched_at=now,
                        error="non-html",
                    )
                # Let requests pick encoding from headers; fall back to apparent.
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding or "utf-8"
                html = resp.text
                try:
                    soup = BeautifulSoup(html, "lxml")
                except Exception:  # noqa: BLE001 - be defensive against malformed HTML
                    soup = BeautifulSoup(html, "html.parser")
                text = _extract_visible_text(soup)
                links = self._extract_links(soup, url)
                return PageSnapshot(
                    url=url,
                    status=resp.status_code,
                    html=html,
                    text=text,
                    content_type=content_type,
                    fetched_at=now,
                    links_found=links,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                log.warning("Network error on %s (attempt %d/%d): %s",
                            url, attempt, self.config.max_retries, exc)
                self._interruptible_sleep(1.5 * attempt)
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Request error on %s: %s", url, exc)
                break
            except Exception as exc:  # noqa: BLE001 - never crash the crawl
                last_exc = exc
                log.exception("Unexpected error on %s", url)
                break
        return PageSnapshot(
            url=url, status=0, html="", text="", content_type="",
            fetched_at=now, error=f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown",
        )

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        out: List[str] = []
        seen_local: Set[str] = set()
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            scheme = urlparse(absolute).scheme.lower()
            if scheme not in {"http", "https"}:
                continue
            canon = _canonicalize(absolute)
            if canon in seen_local:
                continue
            seen_local.add(canon)
            out.append(canon)
        return out
