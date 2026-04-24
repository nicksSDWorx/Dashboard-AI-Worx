# Dutch Tender Scraper

Standalone CLI tool die Nederlandse aanbestedingen voor HRM- en payroll-software
zoekt via officiele, publieke databronnen en de resultaten in een Excel-bestand
wegschrijft. Geen AI, geen persistent geheugen, geen login vereist.

## Bron

Alleen **TenderNed** (`https://www.tenderned.nl`). De tool bevraagt primair
het `papi`-endpoint (JSON) dat TenderNed's eigen website intern gebruikt, en
valt terug op de publieke RSS-feed als het papi-endpoint niet bereikbaar is.

Het TenderNed `papi`-endpoint is ongedocumenteerd en kan wijzigen; bij fouten
valt de tool stil terug op de RSS-feed.

## Filter-criteria

**CPV-codes (breed):**
- 48450000 (HR/time accounting) + 48440000 (financial/accounting)
- 48000000 (software package) + 72260000 (software services)
- 72200000 (programming) + 72500000 (computer services)
- 48200000 (networks) + 48300000 (document software)

**Keywords (NL + EN):** HRM, HR software, personeelsinformatiesysteem, HRMS,
salarisadministratie, salarisverwerkingssoftware, payroll, payrollsoftware,
personeels- en salarisadministratie, HR systeem, personeelssysteem, e-HRM,
tijdregistratie, workforce management, HCM, human capital management,
SaaS, cloud, cloudoplossing.

**Inclusie-regel:** een tender wordt meegenomen als een van de CPV-codes
matcht. Keyword-matches zijn **niet vereist** voor inclusie maar verhogen
de relevance-score. Uitzondering: als een bron (bv. RSS-fallback) geen
CPV-codes meelevert, valt de tool terug op keyword-match.

**Publicatietypes:** alle types (opdracht-aankondigingen, vooraankondigingen,
gunningen, wijzigingen) - geen filter op publicatieType.

## Output

Excel-bestand met de volgende kolommen:

```
Bron | Titel | Aanbestedende dienst | Publicatiedatum | Deadline |
Geschatte waarde (EUR) | CPV-codes | Scope (eerste 500 tekens) |
Referentienummer | URL | Matched keywords | Relevance score (1-5)
```

Rijen worden gesorteerd op relevance score (hoog naar laag) en daarna op
publicatiedatum (nieuw naar oud).

## Gebruik

```
DutchTenderScraper.exe [--days N] [--since YYYY-MM-DD] [--output path.xlsx] [--verbose]
```

- `--days N` : aantal dagen terug zoeken (default 120)
- `--since YYYY-MM-DD` : zoek vanaf een exacte datum. Overschrijft `--days`.
- `--output` : doelpad voor het Excel-bestand (default
  `dutch-tender-scraper_YYYYMMDD_HHMMSS.xlsx` naast de .exe)
- `--verbose` : DEBUG-logging naar stderr (toon per pagina hoeveel binnenkwam)

Voorbeeld: alles vanaf 1 januari 2026:

```
DutchTenderScraper.exe --since 2026-01-01 --verbose
```

Dubbelklik op de .exe opent een console, voert de zoekopdracht uit, toont het
aantal gevonden resultaten en wacht op Enter voor sluiten.

## Een .exe verkrijgen

Er zijn drie manieren; kies wat het handigst is.

### Optie 1 (aanbevolen, geen installatie nodig): download van GitHub Actions

Elke push naar deze branch draait automatisch een Windows-build op GitHub.
De `.exe` wordt teruggecommit naar `tender-scraper/dist/DutchTenderScraper.exe`
en is ook als "Artifact" te downloaden op de Actions-pagina:
`https://github.com/nicksSDWorx/Dashboard-AI-Worx/actions`.

Je hoeft dan zelf niets te bouwen - trek gewoon de nieuwste versie van de
branch en de .exe staat er.

### Optie 2 (lokaal bouwen, 1 klik): dubbelklik `build.bat`

Vereist alleen Python 3.11+ op PATH. `build.bat` is self-contained: het
maakt een venv aan, installeert dependencies, draait PyInstaller, toont
het resultaat en wacht op Enter. Geen PowerShell-policy-gedoe.

Python ontbreekt? `build.bat` vertelt je precies wat je moet doen:

```
winget install -e --id Python.Python.3.11
```

of download via `https://www.python.org/downloads/windows/`.

### Optie 3 (lokaal bouwen via PowerShell): `build.ps1`

```
.\build.ps1                  # venv + pip install + pyinstaller
.\build.ps1 -SmokeTest       # idem, plus een test-run van de .exe achteraf
```

In alle gevallen: de executable komt in `dist\DutchTenderScraper.exe`
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

- Alleen TenderNed - geen EU-tenders (TED) of Aanbestedingskalender.
- Geen AI-analyse. Filtering is louter deterministisch op CPV en keywords.
- TenderNed `papi`-endpoint is ongedocumenteerd; bij wijzigingen valt de tool
  terug op RSS met een kleinere set velden (geen CPV-codes, geen deadline).
- Geen persistent geheugen: elke run start blanco.
