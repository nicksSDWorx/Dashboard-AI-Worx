# Dutch Tender Scraper

Standalone CLI tool die Nederlandse aanbestedingen voor HRM- en payroll-software
zoekt via officiele, publieke databronnen en de resultaten in een Excel-bestand
wegschrijft. Geen AI, geen persistent geheugen, geen login vereist.

## Bronnen

| Bron | Type | Rol |
|---|---|---|
| TED Europa API v3 (`api.ted.europa.eu`) | JSON | Primaire bron voor EU-drempel Nederlandse aanbestedingen |
| TenderNed (`papi` + RSS fallback) | JSON / RSS | Nederlandse publieke en semi-publieke tenders |
| Aanbestedingskalender (`rss`) | RSS | Best-effort aanvullende feed |

Als een bron niet bereikbaar is of zijn endpoint heeft veranderd, loopt de tool
gewoon door met de andere bronnen en wordt een waarschuwing gelogd. Het
TenderNed `papi`-endpoint is ongedocumenteerd en kan instabiel zijn; in dat
geval valt de tool terug op de RSS-feed.

## Filter-criteria

**CPV-codes:** 48450000 (HR-software), 48440000, 48000000, 72260000.

**Keywords (NL + EN):** HRM, HR software, personeelsinformatiesysteem, HRMS,
salarisadministratie, salarisverwerkingssoftware, payroll, payrollsoftware,
personeels- en salarisadministratie, HR systeem, personeelssysteem, e-HRM,
tijdregistratie, workforce management, HCM, human capital management.

Een tender wordt meegenomen als **of** een van de CPV-codes matcht **of** er
minstens een keyword in titel of omschrijving voorkomt.

## Output

Excel-bestand met de volgende kolommen:

```
Bron | Titel | Aanbestedende dienst | Publicatiedatum | Deadline |
Geschatte waarde (EUR) | CPV-codes | Scope (eerste 500 tekens) |
Referentienummer | URL | Matched keywords | Relevance score (1-5)
```

Rijen worden gesorteerd op relevance score (hoog naar laag) en daarna op
publicatiedatum (nieuw naar oud). Duplicaten over TED en TenderNed worden
samengevoegd op referentienummer; als dat niet beschikbaar is, op (titel,
aanbestedende dienst, publicatiedatum).

## Gebruik

```
DutchTenderScraper.exe [--days N] [--output path.xlsx] [--verbose]
```

- `--days N` : aantal dagen terug zoeken (default 60)
- `--output` : doelpad voor het Excel-bestand (default
  `dutch-tender-scraper_YYYYMMDD_HHMMSS.xlsx` naast de .exe)
- `--verbose` : DEBUG-logging naar stderr

Dubbelklik op de .exe opent een console, voert de zoekopdracht uit, toont het
aantal gevonden resultaten en wacht op Enter voor sluiten.

## Bouwen (Windows)

Vereist: Python 3.11+ op PATH, PowerShell.

```
.\build.ps1                  # venv + pip install + pyinstaller
.\build.ps1 -SmokeTest       # idem, plus een test-run van de .exe achteraf
.\build.bat                  # wrapper als `.ps1` niet direct mag draaien
```

Na een succesvolle build vind je de executable in `dist\DutchTenderScraper.exe`
(verwachte grootte ~15-20 MB).

## Lokaal draaien zonder .exe

```
python -m venv venv
.\venv\Scripts\activate          # Windows
source venv/bin/activate         # Linux/macOS
pip install -r requirements.txt
python dutch_tender_scraper.py --days 90 --verbose
```

## Windows SmartScreen

De .exe is niet code-signed. Bij de eerste start kan SmartScreen waarschuwen.
Klik "More info" en dan "Run anyway". Dit is hetzelfde gedrag als de andere
tools in deze repo (BrokenURLFinder, PDF_Merger_Desktop).

## Beperkingen

- Geen AI-analyse of natuurtaal-redeneren. Filtering is louter deterministisch.
- Private-sector buyer-intent signalen (Appwiki, SelectHRM, etc.) zitten
  **niet** in deze tool; die platformen zijn niet via open API beschikbaar.
- TenderNed `papi`-endpoint is ongedocumenteerd; bij wijzigingen valt de tool
  terug op RSS met een kleinere set velden (geen CPV-codes, geen deadline).
- Geen persistent geheugen: elke run start blanco.
