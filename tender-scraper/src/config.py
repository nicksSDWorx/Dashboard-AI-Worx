from __future__ import annotations

DEFAULT_DAYS = 120
HTTP_TIMEOUT = 30

# Inclusie: alle tenders met een van deze CPV-codes wordt meegenomen.
# Smalle HRM/payroll codes staan bovenaan zodat ze in de score blijven wegen.
CPV_CODES = [
    "48450000",  # HR/time accounting software
    "48440000",  # Financial analysis and accounting software
    "48000000",  # Software package and information systems
    "72260000",  # Software-related services
    "72200000",  # Software programming and consultancy
    "72500000",  # Computer-related services
    "48200000",  # Networking, internet and intranet software
    "48300000",  # Document creation, drawing, imaging software
]

DIRECT_HIT_CPV_CODES = {"48450000", "48440000"}

# Keywords verhogen alleen de relevance-score; ze zijn niet meer vereist voor
# inclusie (keuze 3d: CPV-match volstaat).
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
    "SaaS",
    "cloud",
    "cloudoplossing",
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
