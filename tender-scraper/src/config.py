from __future__ import annotations

DEFAULT_DAYS = 60
HTTP_TIMEOUT = 30
USER_AGENT = "DutchTenderScraper/1.0 (+https://github.com/nickssdworx/dashboard-ai-worx)"

COUNTRY_CODE_ISO2 = "NL"
COUNTRY_CODE_ISO3 = "NLD"

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

TED_PRIMARY_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_FALLBACK_URL = "https://ted.europa.eu/api/v3.0/notices/search"
TED_DETAIL_URL_TEMPLATE = "https://ted.europa.eu/en/notice/-/detail/{publication_number}"

TENDERNED_PAPI_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
TENDERNED_RSS_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties/rss"
TENDERNED_DETAIL_URL_TEMPLATE = "https://www.tenderned.nl/aankondigingen/overzicht/{publicatie_id}"

AANBESTEDINGSKALENDER_RSS_URL = "https://www.aanbestedingskalender.nl/rss"

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
