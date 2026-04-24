@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem   Dutch Tender Scraper - one-click build script
rem   Double-click this file to build dist\DutchTenderScraper.exe
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   Dutch Tender Scraper - one-click builder
echo ============================================================
echo.

rem --- Locate a working Python 3.11+ --------------------------
set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3.11"
)
if "%PY_CMD%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=python"
    )
)
if "%PY_CMD%"=="" (
    echo [ERROR] Python 3.11 of nieuwer is niet gevonden op deze machine.
    echo.
    echo Installeer Python 3.11 of nieuwer via:
    echo   - winget install -e --id Python.Python.3.11
    echo   - of download van https://www.python.org/downloads/windows/
    echo.
    echo Vergeet niet "Add Python to PATH" aan te vinken tijdens de installatie.
    echo.
    goto :end_error
)

echo [1/5] Python gevonden: %PY_CMD%
%PY_CMD% --version
echo.

rem --- Create virtual environment -----------------------------
if not exist "venv\Scripts\python.exe" (
    echo [2/5] Virtual environment aanmaken in .\venv ...
    %PY_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Virtual environment aanmaken is mislukt.
        goto :end_error
    )
) else (
    echo [2/5] Virtual environment bestaat al in .\venv
)
echo.

set "VENV_PY=%~dp0venv\Scripts\python.exe"

rem --- Upgrade pip and install dependencies -------------------
echo [3/5] pip upgraden en dependencies installeren ...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] pip upgrade is mislukt.
    goto :end_error
)
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install is mislukt.
    goto :end_error
)
echo.

rem --- Clean previous build artifacts -------------------------
echo [4/5] Oude build-bestanden opruimen ...
if exist "build" rmdir /s /q "build"
if exist "dist\DutchTenderScraper.exe" del /q "dist\DutchTenderScraper.exe"
echo.

rem --- Run PyInstaller ----------------------------------------
echo [5/5] PyInstaller uitvoeren (dit kan 1-2 minuten duren) ...
"%VENV_PY%" -m PyInstaller --clean --noconfirm DutchTenderScraper.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller is mislukt.
    goto :end_error
)

if not exist "dist\DutchTenderScraper.exe" (
    echo [ERROR] De .exe is niet geproduceerd in dist\
    goto :end_error
)

rem --- Success -------------------------------------------------
echo.
echo ============================================================
echo   BUILD GELUKT
echo ============================================================
echo.
echo   Bestand:  %~dp0dist\DutchTenderScraper.exe
for %%F in ("dist\DutchTenderScraper.exe") do echo   Grootte:  %%~zF bytes
echo.
echo   Dubbelklik de .exe om de scraper te draaien.
echo.
pause
exit /b 0

:end_error
echo.
echo ============================================================
echo   BUILD MISLUKT - zie melding hierboven
echo ============================================================
echo.
pause
exit /b 1
