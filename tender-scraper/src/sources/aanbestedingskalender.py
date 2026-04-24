from __future__ import annotations

import logging
from typing import List

from ..models import Tender


def fetch_aanbestedingskalender(days: int, logger: logging.Logger) -> List[Tender]:
    """Aanbestedingskalender wordt overgeslagen.

    Er is geen publieke RSS- of JSON-feed bevestigd voor Aanbestedingskalender
    (documentatie verwijst alleen naar email-alerts en ingelogde smart-search
    profielen). Tot dat verandert laten we de bron ongebruikt en vertrouwen
    we op TED en TenderNed.
    """
    logger.debug(
        "Aanbestedingskalender overgeslagen: geen werkende publieke feed bevestigd"
    )
    return []
