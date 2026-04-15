#!/usr/bin/env python3
"""
SDWorx 404 Link Checker Agent — v2
Crawls sdworx.nl, detecteert kapotte links inclusief linktekst,
en stuurt automatisch een HTML-rapport naar melanie.brugel@sdworx.com.

Vereisten : Python 3.10+  (alleen stdlib — geen pip nodig)

Gebruik:
    python3 sdworx_checker_v2.py
    python3 sdworx_checker_v2.py --max 10000 --concurrency 15
    python3 sdworx_checker_v2.py --smtp-host mail.sdworx.com --smtp-user melanie.brugel@sdworx.com
    python3 sdworx_checker_v2.py --no-email        # alleen rapport, geen mail
"""

import asyncio
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from dataclasses import dataclass, field
from datetime import datetime
import argparse
import sys
import ssl
import smtplib
import getpass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Config ────────────────────────────────────────────────────────────────────

SEED_URL       = "https://www.sdworx.nl"
DOMAIN         = "sdworx.nl"
MAX_PAGES      = 10000
CONCURRENCY    = 8
TIMEOUT        = 12
DELAY          = 0.15

EMAIL_TO       = "melanie.brugel@sdworx.com"
EMAIL_FROM     = "noreply-linkchecker@sdworx.com"   # pas aan
SMTP_HOST      = "localhost"                          # pas aan (zie --help)
SMTP_PORT      = 587

SKIP_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".pdf", ".zip", ".css", ".js", ".woff", ".woff2",
    ".ttf", ".ico", ".mp4", ".mp3", ".eot", ".map",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SDWorxLinkChecker/2.0; Python-stdlib)",
    "Accept":     "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "nl,en;q=0.8",
}

# ── HTML parser: links + tekst ────────────────────────────────────────────────

@dataclass
class RawLink:
    href: str
    text: str = ""

class LinkParser(HTMLParser):
    """Extracts <a href="…">link text</a> pairs."""

    def __init__(self):
        super().__init__()
        self.raw_links: list[RawLink] = []
        self._current: RawLink | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = ""
            for name, val in attrs:
                if name == "href" and val:
                    href = val.strip()
            self._current = RawLink(href=href)
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._current is not None:
            self._current.text = " ".join("".join(self._buf).split()).strip()
            self.raw_links.append(self._current)
            self._current = None
            self._buf = []

    def handle_data(self, data):
        if self._current is not None:
            self._buf.append(data)

    def handle_entityref(self, name):
        if self._current is not None:
            self._buf.append(f"&{name};")

    def handle_charref(self, name):
        if self._current is not None:
            self._buf.append(f"&#{name};")


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return list of (absolute_url, link_text) for internal links."""
    parser = LinkParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    seen   = set()
    result = []

    for rl in parser.raw_links:
        raw = rl.href
        if not raw or raw.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            abs_url = urllib.parse.urljoin(base_url, raw)
            parsed  = urllib.parse.urlparse(abs_url)
            clean   = urllib.parse.urlunparse(parsed._replace(fragment="", query=""))
            if clean.startswith("http") and DOMAIN in parsed.netloc and clean not in seen:
                seen.add(clean)
                text = rl.text or "(geen linktekst)"
                result.append((clean, text))
        except Exception:
            pass

    return result

# ── HTTP fetch ────────────────────────────────────────────────────────────────

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode    = ssl.CERT_NONE


def sync_fetch(url: str) -> tuple:
    """Returns (status, html). Runs in thread pool."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx) as resp:
            status   = resp.status
            ct       = resp.headers.get("Content-Type", "")
            html     = ""
            path     = urllib.parse.urlparse(url).path.lower()
            is_asset = any(path.endswith(e) for e in SKIP_EXT)
            if status < 400 and "html" in ct and not is_asset:
                raw  = resp.read(500_000)
                enc  = resp.headers.get_content_charset("utf-8")
                html = raw.decode(enc, errors="replace")
            return status, html
    except urllib.error.HTTPError as e:
        return e.code, ""
    except urllib.error.URLError:
        return "ERR", ""
    except TimeoutError:
        return "TIMEOUT", ""
    except Exception:
        return "ERR", ""

# ── ANSI kleuren ──────────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty()

class C:
    RESET  = "\033[0m"  if USE_COLOR else ""
    RED    = "\033[91m" if USE_COLOR else ""
    GREEN  = "\033[92m" if USE_COLOR else ""
    YELLOW = "\033[93m" if USE_COLOR else ""
    CYAN   = "\033[96m" if USE_COLOR else ""
    PURPLE = "\033[95m" if USE_COLOR else ""
    GRAY   = "\033[90m" if USE_COLOR else ""
    BOLD   = "\033[1m"  if USE_COLOR else ""

def fmt_status(status) -> str:
    s = str(status)
    if status in (404, 410) or status in ("ERR", "TIMEOUT"):
        return f"{C.RED}{C.BOLD}[{s}]{C.RESET}"
    if isinstance(status, int) and 200 <= status < 300:
        return f"{C.GREEN}[{s}]{C.RESET}"
    if isinstance(status, int) and 300 <= status < 400:
        return f"{C.CYAN}[{s}]{C.RESET}"
    return f"{C.YELLOW}[{s}]{C.RESET}"

# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class Result:
    url:       str
    status:    object
    link_text: str = "(geen linktekst)"
    found_on:  str = "—"

    @property
    def is_broken(self) -> bool:
        return self.status in (404, 410) or self.status in ("ERR", "TIMEOUT")

    @property
    def status_label(self) -> str:
        return str(self.status)

# ── Agent ─────────────────────────────────────────────────────────────────────

class LinkCheckerAgent:
    def __init__(self, max_pages: int, concurrency: int):
        self.max_pages   = max_pages
        self.concurrency = concurrency
        # visited stores (url, link_text) → we track url set separately
        self.visited_urls: set  = set()
        # queue items: (url, link_text, found_on_url)
        self.queue              = asyncio.Queue()
        self.results: list[Result] = []
        self.sem                = asyncio.Semaphore(concurrency)
        self._lock              = asyncio.Lock()

    async def process(self, loop, url: str, link_text: str, found_on: str):
        await asyncio.sleep(DELAY)
        async with self.sem:
            status, html = await loop.run_in_executor(None, sync_fetch, url)

        result = Result(url=url, status=status, link_text=link_text, found_on=found_on)
        async with self._lock:
            self.results.append(result)

        icon  = "❌" if result.is_broken else ("↪ " if isinstance(status, int) and status >= 300 else "✅")
        trunc = (url[:80] + "…") if len(url) > 80 else url
        txt   = (link_text[:30] + "…") if len(link_text) > 30 else link_text
        print(f"  {icon} {fmt_status(status)}  {C.GRAY}{trunc}{C.RESET}")
        if result.is_broken:
            print(f"         {C.RED}tekst  : \"{txt}\"{C.RESET}")
            print(f"         {C.GRAY}pagina : {found_on}{C.RESET}")

        # Crawl further into this page
        if html and not result.is_broken:
            new_links = extract_links(html, url)
            async with self._lock:
                for link_url, ltext in new_links:
                    if link_url not in self.visited_urls and len(self.visited_urls) < self.max_pages:
                        self.visited_urls.add(link_url)
                        await self.queue.put((link_url, ltext, url))

    async def run(self):
        loop  = asyncio.get_event_loop()
        start = datetime.now()

        print(f"\n{C.PURPLE}{C.BOLD}🕷️  SDWorx 404 Link Checker Agent v2{C.RESET}")
        print(f"{C.GRAY}   Seed        : {SEED_URL}")
        print(f"   Max pages   : {self.max_pages}")
        print(f"   Concurrency : {self.concurrency}")
        print(f"   Gestart     : {start.strftime('%H:%M:%S')}{C.RESET}")
        print(f"\n{'─'*70}\n")

        self.visited_urls.add(SEED_URL)
        await self.queue.put((SEED_URL, "Homepage", "—"))

        pending: set = set()

        while True:
            while not self.queue.empty() and len(pending) < self.concurrency:
                if len(self.results) + len(pending) >= self.max_pages:
                    break
                url, link_text, found_on = await self.queue.get()
                task = asyncio.create_task(self.process(loop, url, link_text, found_on))
                pending.add(task)
                task.add_done_callback(pending.discard)

            if not pending:
                break

            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            if len(self.results) >= self.max_pages:
                for t in pending:
                    t.cancel()
                break

        return (datetime.now() - start).total_seconds()

# ── Rapport: tekst ────────────────────────────────────────────────────────────

def build_txt_report(results: list[Result], duration: float) -> str:
    broken = [r for r in results if r.is_broken]
    ok     = [r for r in results if not r.is_broken]
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("=" * 70)
    lines.append("  SDWorx 404 Link Checker — Rapport")
    lines.append(f"  Gegenereerd : {ts}")
    lines.append(f"  Website     : {SEED_URL}")
    lines.append("=" * 70)
    lines.append(f"\n  Gecheckt    : {len(results)} URLs")
    lines.append(f"  OK (2xx/3xx): {len(ok)}")
    lines.append(f"  Kapot       : {len(broken)}")
    lines.append(f"  Duur        : {duration:.1f} seconden\n")

    if broken:
        lines.append("─" * 70)
        lines.append(f"  KAPOTTE LINKS ({len(broken)})")
        lines.append("─" * 70 + "\n")
        for i, r in enumerate(broken, 1):
            lines.append(f"  {i:>3}. Status    : {r.status_label}")
            lines.append(f"       Linktekst : {r.link_text}")
            lines.append(f"       URL       : {r.url}")
            lines.append(f"       Gevonden  : {r.found_on}")
            lines.append("")
    else:
        lines.append("  ✅ Geen kapotte links gevonden!\n")

    lines.append("─" * 70)
    lines.append("  ALLE GECHECKTE URLS")
    lines.append("─" * 70 + "\n")
    for r in results:
        lines.append(f"  [{r.status_label:>7}]  {r.url}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)

# ── Rapport: HTML (voor de e-mail) ────────────────────────────────────────────

def build_html_report(results: list[Result], duration: float) -> str:
    broken = [r for r in results if r.is_broken]
    ok     = [r for r in results if not r.is_broken]
    ts     = datetime.now().strftime("%d %B %Y om %H:%M")

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    broken_rows = ""
    for i, r in enumerate(broken, 1):
        bg = "#fff5f5" if i % 2 == 0 else "#fff0f0"
        broken_rows += f"""
        <tr style="background:{bg}">
          <td style="padding:10px 12px;font-weight:700;color:#c0392b;font-family:monospace">{esc(r.status_label)}</td>
          <td style="padding:10px 12px;color:#555">{esc(r.link_text)}</td>
          <td style="padding:10px 12px"><a href="{esc(r.url)}" style="color:#c0392b;word-break:break-all">{esc(r.url)}</a></td>
          <td style="padding:10px 12px;color:#888;font-size:12px;word-break:break-all">{esc(r.found_on)}</td>
        </tr>"""

    all_rows = ""
    for i, r in enumerate(results, 1):
        bg    = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        color = "#c0392b" if r.is_broken else ("#888" if isinstance(r.status, int) and r.status >= 300 else "#27ae60")
        all_rows += f"""
        <tr style="background:{bg}">
          <td style="padding:8px 12px;font-family:monospace;color:{color};font-weight:{'700' if r.is_broken else '400'}">{esc(r.status_label)}</td>
          <td style="padding:8px 12px;font-size:12px;color:#555">{esc(r.link_text)}</td>
          <td style="padding:8px 12px;font-size:12px"><a href="{esc(r.url)}" style="color:#2980b9;word-break:break-all">{esc(r.url)}</a></td>
        </tr>"""

    broken_section = ""
    if broken:
        broken_section = f"""
      <h2 style="color:#c0392b;margin-top:36px">🚨 Kapotte links ({len(broken)})</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #f5c6cb;border-radius:6px;overflow:hidden;margin-top:12px">
        <thead>
          <tr style="background:#c0392b;color:#fff">
            <th style="padding:10px 12px;text-align:left;white-space:nowrap">Status</th>
            <th style="padding:10px 12px;text-align:left">Linktekst</th>
            <th style="padding:10px 12px;text-align:left">Kapotte URL</th>
            <th style="padding:10px 12px;text-align:left">Gevonden op pagina</th>
          </tr>
        </thead>
        <tbody>{broken_rows}</tbody>
      </table>"""
    else:
        broken_section = """
      <div style="background:#d4edda;border:1px solid #c3e6cb;border-radius:6px;padding:16px;margin-top:24px;color:#155724">
        ✅ Geen kapotte links gevonden op sdworx.nl.
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SDWorx 404 Link Checker Rapport</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif;color:#333">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:32px 0">
    <tr><td align="center">
      <table width="720" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">

        <!-- Header -->
        <tr>
          <td style="background:#003c8f;padding:28px 36px">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">🕷️ SDWorx Link Checker Rapport</h1>
            <p style="margin:6px 0 0;color:#adc6ff;font-size:14px">Automatisch gegenereerd op {ts}</p>
          </td>
        </tr>

        <!-- Body -->
        <tr><td style="padding:28px 36px">

          <!-- Stats -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              {"".join(f'''<td align="center" style="background:#f0f4ff;border-radius:8px;padding:18px 10px;width:25%">
                <div style="font-size:28px;font-weight:700;color:{col}">{val}</div>
                <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:1px">{lbl}</div>
              </td>''' for val, lbl, col in [
                  (len(results), "Gecheckt", "#003c8f"),
                  (len(ok),      "OK",        "#27ae60"),
                  (len(broken),  "Kapot",     "#c0392b"),
                  (f"{duration:.0f}s", "Duur", "#888"),
              ])}
            </tr>
          </table>

          {broken_section}

          <!-- All URLs -->
          <h2 style="color:#333;margin-top:36px;font-size:16px">Alle gecheckte URLs</h2>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;font-size:13px">
            <thead>
              <tr style="background:#003c8f;color:#fff">
                <th style="padding:9px 12px;text-align:left;white-space:nowrap">Status</th>
                <th style="padding:9px 12px;text-align:left">Linktekst</th>
                <th style="padding:9px 12px;text-align:left">URL</th>
              </tr>
            </thead>
            <tbody>{all_rows}</tbody>
          </table>

        </td></tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f4f6f8;padding:16px 36px;font-size:12px;color:#aaa;text-align:center;border-top:1px solid #e0e0e0">
            SDWorx Link Checker · {SEED_URL} · {ts}
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

# ── E-mail versturen ──────────────────────────────────────────────────────────

def send_email(
    html_body:   str,
    txt_body:    str,
    broken_count: int,
    smtp_host:   str,
    smtp_port:   int,
    smtp_user:   str | None,
    smtp_pass:   str | None,
    use_tls:     bool,
):
    subject = (
        f"[SDWorx Link Checker] {'🚨 ' + str(broken_count) + ' kapotte links gevonden' if broken_count else '✅ Geen kapotte links'} — {datetime.now().strftime('%d-%m-%Y')}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    msg.attach(MIMEText(txt_body,  "plain",  "utf-8"))
    msg.attach(MIMEText(html_body, "html",   "utf-8"))

    print(f"\n{C.CYAN}📧  E-mail versturen naar {EMAIL_TO}...{C.RESET}")
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        server.quit()
        print(f"{C.GREEN}✅  E-mail succesvol verzonden!{C.RESET}")
    except Exception as e:
        print(f"{C.RED}❌  E-mail mislukt: {e}{C.RESET}")
        print(f"{C.GRAY}   Controleer SMTP-instellingen (--smtp-host, --smtp-user, --smtp-port){C.RESET}")

# ── Console samenvatting ──────────────────────────────────────────────────────

def print_summary(results: list[Result], duration: float):
    broken = [r for r in results if r.is_broken]
    ok     = [r for r in results if not r.is_broken]

    print(f"\n{'─'*70}")
    print(f"{C.BOLD}{C.PURPLE}📊  CRAWL AFGEROND{C.RESET}")
    print(f"{'─'*70}")
    print(f"  ⏱  Duur       : {duration:.1f}s")
    print(f"  🔗 Gecheckt   : {len(results)}")
    print(f"  {C.GREEN}✅ OK         : {len(ok)}{C.RESET}")
    print(f"  {C.RED}❌ Kapot      : {len(broken)}{C.RESET}")

    if broken:
        print(f"\n{'─'*70}")
        print(f"{C.BOLD}{C.RED}🚨  KAPOTTE LINKS ({len(broken)}){C.RESET}")
        print(f"{'─'*70}")
        for i, r in enumerate(broken, 1):
            print(f"\n  {i:>3}. {C.RED}{C.BOLD}[{r.status}]{C.RESET}  {r.url}")
            print(f"       {C.YELLOW}Tekst   :{C.RESET} {r.link_text}")
            print(f"       {C.GRAY}Pagina  : {r.found_on}{C.RESET}")
    else:
        print(f"\n  {C.GREEN}{C.BOLD}🎉  Geen kapotte links gevonden!{C.RESET}")

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="SDWorx 404 Link Checker — crawlt sdworx.nl en stuurt rapport per e-mail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python3 sdworx_checker_v2.py
  python3 sdworx_checker_v2.py --max 500 --concurrency 12
  python3 sdworx_checker_v2.py --smtp-host mail.sdworx.com --smtp-user noreply@sdworx.com
  python3 sdworx_checker_v2.py --no-email --output mijn_rapport
        """,
    )
    p.add_argument("--max",         type=int,  default=MAX_PAGES,
                   help=f"Max paginas (default: {MAX_PAGES})")
    p.add_argument("--concurrency", type=int,  default=CONCURRENCY,
                   help=f"Parallelle requests (default: {CONCURRENCY})")
    p.add_argument("--output",      type=str,  default="sdworx_rapport",
                   help="Basisnaam output bestand (zonder extensie)")
    p.add_argument("--no-email",    action="store_true",
                   help="Geen e-mail versturen, alleen bestanden opslaan")
    p.add_argument("--smtp-host",   type=str,  default=SMTP_HOST,
                   help=f"SMTP server (default: {SMTP_HOST})")
    p.add_argument("--smtp-port",   type=int,  default=SMTP_PORT,
                   help=f"SMTP poort (default: {SMTP_PORT})")
    p.add_argument("--smtp-user",   type=str,  default=None,
                   help="SMTP gebruikersnaam (optioneel)")
    p.add_argument("--smtp-pass",   type=str,  default=None,
                   help="SMTP wachtwoord (optioneel; wordt anders gevraagd)")
    p.add_argument("--smtp-ssl",    action="store_true",
                   help="Gebruik SSL in plaats van STARTTLS")
    return p.parse_args()


async def main():
    args  = parse_args()
    agent = LinkCheckerAgent(max_pages=args.max, concurrency=args.concurrency)

    try:
        duration = await agent.run()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}⛔ Gestopt door gebruiker.{C.RESET}")
        duration = 0

    results = agent.results
    broken  = [r for r in results if r.is_broken]

    # Console samenvatting
    print_summary(results, duration)

    # Rapporten opbouwen
    txt_body  = build_txt_report(results, duration)
    html_body = build_html_report(results, duration)

    # Tekstrapport opslaan
    txt_path = args.output + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_body)

    # HTML rapport opslaan
    html_path = args.output + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)

    print(f"\n  📄 Tekstrapport → {C.CYAN}{txt_path}{C.RESET}")
    print(f"  🌐 HTML rapport → {C.CYAN}{html_path}{C.RESET}")

    # E-mail
    if not args.no_email:
        smtp_pass = args.smtp_pass
        if args.smtp_user and not smtp_pass:
            smtp_pass = getpass.getpass(f"  SMTP wachtwoord voor {args.smtp_user}: ")

        send_email(
            html_body    = html_body,
            txt_body     = txt_body,
            broken_count = len(broken),
            smtp_host    = args.smtp_host,
            smtp_port    = args.smtp_port,
            smtp_user    = args.smtp_user,
            smtp_pass    = smtp_pass,
            use_tls      = not args.smtp_ssl,
        )
    else:
        print(f"\n  {C.GRAY}(e-mail overgeslagen via --no-email){C.RESET}")

    print(f"\n{'─'*70}\n")


if __name__ == "__main__":
    asyncio.run(main())