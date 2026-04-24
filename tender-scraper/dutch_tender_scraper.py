from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

from src.config import DEFAULT_DAYS
from src.dedupe import dedupe
from src.excel_writer import write_xlsx
from src.filtering import match_tender
from src.logging_setup import get_logger
from src.scoring import score
from src.sources import fetch_all_sources


def _parse_since(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--since verwacht formaat YYYY-MM-DD, kreeg '{value}'"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="DutchTenderScraper",
        description="Zoek Nederlandse aanbestedingen voor HRM/payroll software via TenderNed.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Aantal dagen terug te zoeken (default: {DEFAULT_DAYS}). "
        f"Genegeerd als --since is opgegeven.",
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        help="Zoek vanaf deze datum (YYYY-MM-DD). Overschrijft --days.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Pad naar output .xlsx bestand (default: auto-timestamped in huidige map)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose (DEBUG) logging",
    )
    return parser.parse_args()


def _default_output_path() -> Path:
    base_dir = Path(sys.argv[0]).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_dir / f"dutch-tender-scraper_{stamp}.xlsx"


def _likely_double_click() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    if os.environ.get("PROMPT") or os.environ.get("PSModulePath") and os.environ.get("TERM_PROGRAM"):
        return False
    try:
        return sys.stdin is None or not sys.stdin.isatty() or sys.stdout.isatty()
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    logger = get_logger(verbose=args.verbose)

    output_path = args.output or _default_output_path()

    if args.since:
        days = max(1, (date.today() - args.since).days)
        logger.info("Zoekvenster: vanaf %s (%d dagen)", args.since.isoformat(), days)
    else:
        days = args.days
        logger.info("Zoekvenster: laatste %d dagen", days)
    logger.info("Output: %s", output_path)

    raw = fetch_all_sources(days, logger)
    logger.info("Totaal opgehaald (pre-filter): %d", len(raw))

    filtered = []
    for tender in raw:
        is_match, keywords, cpv_hit = match_tender(tender)
        if not is_match:
            continue
        tender.matched_keywords = keywords
        tender.relevance_score = score(tender, cpv_hit, keywords)
        filtered.append(tender)

    logger.info("Na filter: %d", len(filtered))

    deduped = dedupe(filtered)
    logger.info("Na dedupe: %d", len(deduped))

    try:
        write_xlsx(deduped, output_path)
    except PermissionError as exc:
        logger.error("%s", exc)
        print(f"Bestand kon niet worden geschreven: {exc}")
        _wait_if_needed()
        return 1
    except Exception as exc:
        logger.error("Excel schrijven mislukt: %s", exc)
        _wait_if_needed()
        return 1

    print(f"Gevonden: {len(deduped)} relevante aanbestedingen")
    print(f"Resultaat weggeschreven naar: {output_path}")
    _wait_if_needed()
    return 0


def _wait_if_needed() -> None:
    if _likely_double_click():
        try:
            input("Druk op Enter om te sluiten...")
        except EOFError:
            pass


if __name__ == "__main__":
    sys.exit(main())
