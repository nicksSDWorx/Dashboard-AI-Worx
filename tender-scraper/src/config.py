from __future__ import annotations

DEFAULT_DAYS = 60
HTTP_TIMEOUT = 30

CPV_CODES = [
    "48450000",
    "48440000",
    "48000000",
    "72260000",
]

DIRECT_HIT_CPV_CODES = {"48450000", "48440000"}

KEYWORDS = [
    "HRM",
    "HR software",
    "personeelsinformatiesysteem",
    "HRMS",
    "salarisadministratie",
    "salarisverwerkingssoftware",
    "payroll",
    "payrollsoftware",
    "personeels- en salarisadministratie",
    "HR systeem",
    "personeelssysteem",
    "e-HRM",
    "tijdregistratie",
    "workforce management",
    "HCM",
    "human capital management",
]

STRONG_KEYWORDS = {
    "salarisadministratie",
    "HRM",
    "payroll",
    "e-HRM",
}

TENDERNED_PAPI_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
TENDERNED_RSS_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/rss/laatste-publicatie.rss"
TENDERNED_DETAIL_URL_TEMPLATE = "https://www.tenderned.nl/aankondigingen/overzicht/{publicatie_id}"

# Browser-achtige User-Agent werkt beter tegen TenderNed's papi endpoint
# dan een "bot"-achtige string (TenderNed blokkeert sommige bot-UAs met 403).
TENDERNED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

EXCEL_COLUMNS = [
    "Bron",
    "Titel",
    "Aanbestedende dienst",
    "Publicatiedatum",
    "Deadline",
    "Geschatte waarde (EUR)",
    "CPV-codes",
    "Scope",
    "Referentienummer",
    "URL",
    "Matched keywords",
    "Relevance score",
]
