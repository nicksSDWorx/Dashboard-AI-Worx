# AFAS Change Monitor

Een Windows-desktopapplicatie die dagelijks `https://www.afas.nl` volledig scrapet,
wijzigingen in tekst **en** HTML-structuur detecteert, en het resultaat vastlegt in
een Excel-bestand + een side-by-side HTML-rapport.

## Functionaliteit

- Volledige crawl van afas.nl (alleen interne links, respecteert `robots.txt` en `Crawl-delay`)
- Dagelijkse automatische run om `03:00` (instelbaar in `config.yaml`)
- Detectie van **nieuwe**, **verwijderde**, **tekstueel gewijzigde** en **structureel gewijzigde** pagina's
- Configureerbare regex-ignore-lijst voor dynamische content (timestamps, CSRF, cache-busters, ...)
- Excel-bestand `afas_monitor_data.xlsx` met 4 sheets: Overzicht, Pagina's, Wijzigingen, Snapshots
- Side-by-side HTML-rapport (`reports/report_YYYY-MM-DD.html`) met rood/groene diff-kleuring
- Volledige snapshots (HTML + text) als losse bestanden onder `snapshots/`
- Tkinter-GUI met Start/Stop, live log, statusindicator en snelkoppelingen
- Thread-safe: crawl loopt in aparte thread zodat de UI reageert tijdens een run

## Projectstructuur

```
AFAS_Change_Monitor/
├── main.py            # Tkinter GUI + entry point
├── config.py          # YAML config + padfuncties
├── scraper.py         # BFS-crawler met robots.txt
├── differ.py          # Wijzigingsdetectie (pure logica)
├── storage.py         # Excel + snapshot-opslag
├── reporter.py        # HTML rapport (difflib.HtmlDiff)
├── scheduler.py       # APScheduler + run-orkestratie
├── config.yaml        # Runtime-configuratie
├── requirements.txt
├── build.bat          # PyInstaller build-script
├── tests/
│   └── test_differ.py
├── data/              # (auto) Excel output
├── snapshots/         # (auto) HTML/text backups
├── reports/           # (auto) HTML rapporten
└── logs/              # (auto) rotating log files
```

## Installatie (development)

Python 3.10 of nieuwer is vereist.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Gebruik

1. Start de applicatie.
2. Bij de eerste run staat de Excel-database nog leeg — dat is normaal. Klik
   op **Start scan** om een baseline te leggen. Er verschijnen dan
   `Nieuwe pagina` rijen voor alle afas.nl-pagina's.
3. De scheduler draait op de achtergrond (standaard 03:00 Europe/Amsterdam)
   zolang de applicatie open is. De volgende geplande run is zichtbaar in de UI.
4. Na elke run:
   - klik **Open laatste rapport** voor de HTML-weergave;
   - klik **Open Excel data** voor het volledige overzicht in Excel;
   - klik **Open config** om `config.yaml` aan te passen (herstart nodig om
     schedule_time wijzigingen actief te maken).

### Stop

De **Stop scan** knop zet een event dat de crawler netjes aan het einde van de
huidige pagina afbreekt. Alle tot dan toe opgehaalde pagina's worden nog steeds
verwerkt en weggeschreven.

## Bouwen naar `.exe`

Vanuit een Windows-command prompt in deze folder:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
build.bat
```

De output komt in `dist\AFAS Monitor.exe`. `config.yaml` wordt naast de `.exe`
gezet zodat eindgebruikers hem kunnen aanpassen. Desgewenst is een `icon.ico`
in deze folder voldoende om een custom icoon mee te geven — `build.bat` pikt
het automatisch op.

**Tip:** Excel-bestand, snapshots/, reports/ en logs/ worden aangemaakt in de
folder waar de `.exe` draait. Plaats de `.exe` dus op een locatie met
schrijfrechten.

## Excel-formaat

| Sheet | Inhoud |
| ----- | ------ |
| **Overzicht** | 1 rij per scan-run: datum, aantal pagina's, telling per wijzigingstype, pad naar rapport |
| **Pagina's** | 1 rij per unieke URL met status, laatste check, text+structure hash, pad naar laatste snapshot |
| **Wijzigingen** | Append-only historisch log: datum, URL, type wijziging, korte samenvatting |
| **Snapshots** | Append-only log van iedere succesvol opgehaalde pagina met pad naar HTML- en txt-bestand |

Snapshots zelf staan als `snapshots/<slug>__<hash>/<YYYYMMDDHHMMSS>.html` en `.txt`
op schijf; het Excel-bestand bevat alleen verwijzingen, zodat het bestand
beheersbaar blijft bij dagelijkse runs.

## Rapport-formaat

`reports/report_YYYY-MM-DD.html` wordt per run gegenereerd (time-suffix bij meerdere
runs op dezelfde dag). Bovenaan staat een samenvatting per wijzigingstype. Daaronder
komt per gewijzigde pagina:

- URL + badge met het wijzigingstype
- Korte samenvatting
- (bij tekstwijziging) side-by-side `difflib.HtmlDiff` tabel — groen = toegevoegd,
  rood = verwijderd, geel = gewijzigd
- (bij structuurwijziging) identieke diff op de DOM-structuur (tags + id's + classes)

## Configuratie (`config.yaml`)

```yaml
start_url: "https://www.afas.nl"
allowed_domains:
  - "afas.nl"
  - "www.afas.nl"
schedule_time: "03:00"
user_agent: "AFAS-Change-Monitor/1.0"
max_pages: 5000
timeout_seconds: 30
default_crawl_delay_seconds: 2
max_retries: 3
skip_extensions:
  - ".pdf"
  - ".jpg"
  # ...
ignore_patterns:
  - 'csrf[_-]?token["\s:=]+[A-Za-z0-9+/=_-]{8,}'
  - '\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b'
  # ...
```

- `schedule_time` — `HH:MM` in Europe/Amsterdam.
- `max_pages` — harde veiligheidslimiet per run.
- `ignore_patterns` — Python regex, case-insensitive, wordt **vóór** hashing
  toegepast zodat dynamische tokens geen valse wijzigingen veroorzaken.

## Tests

```bat
python -m unittest discover -v tests
```

De testsuite dekt de kern van `differ.py`: normalisatie, structuur-extractie en
alle wijzigingstypes (nieuw / verwijderd / tekst / structuur / geen).

## Logging

Alle modules loggen via de standaard Python `logging` module. Logs verschijnen
tegelijk in:

- het log-venster in de GUI (live);
- `logs/afas_monitor.log` (roteert bij 2 MB, 5 backups).

## Bekende beperkingen

- JavaScript-rendered content wordt niet uitgevoerd; we parsen alleen de HTML
  die de server stuurt. Voor `afas.nl` volstaat dat voor de publieke content.
- Wijzigingen in afbeeldingen worden niet gedetecteerd — alleen HTML + zichtbare
  tekst.
- Bij de eerste scan worden *alle* pagina's als "Nieuwe pagina" gelogd. Dat is
  de bewuste baseline; vanaf run 2 zijn alleen de echte verschillen zichtbaar.
