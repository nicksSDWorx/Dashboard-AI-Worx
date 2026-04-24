@echo off
REM ------------------------------------------------------------------
REM Build a single-file, windowed .exe for AFAS Change Monitor.
REM Run this from a "Command Prompt" in this folder after:
REM     python -m venv .venv
REM     .venv\Scripts\activate
REM     pip install -r requirements.txt
REM ------------------------------------------------------------------
setlocal

REM Clean previous build artifacts.
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
if exist "AFAS Monitor.spec" del "AFAS Monitor.spec"

REM Icon is optional: omit --icon if icon.ico is missing.
set ICON_ARG=
if exist icon.ico set ICON_ARG=--icon=icon.ico

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "AFAS Monitor" ^
    %ICON_ARG% ^
    --add-data "config.yaml;." ^
    --collect-submodules apscheduler ^
    --hidden-import lxml ^
    --hidden-import openpyxl ^
    main.py

if errorlevel 1 (
    echo.
    echo Build FAILED.
    exit /b 1
)

REM Copy editable config next to the .exe so end-users can tweak it.
copy /y config.yaml "dist\config.yaml" >nul

echo.
echo Build OK - see dist\AFAS Monitor.exe
endlocal
