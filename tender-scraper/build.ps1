#Requires -Version 5.0
<#
.SYNOPSIS
  Build DutchTenderScraper.exe via PyInstaller.

.DESCRIPTION
  Creates a local Python venv, installs dependencies, runs PyInstaller against
  DutchTenderScraper.spec, and reports the size + SHA-256 of the resulting
  single-file executable. Run this on a Windows machine with Python 3.11+.

.PARAMETER SmokeTest
  After a successful build, run the .exe with `--days 7 --output smoke.xlsx
  --verbose` to verify that it produces an Excel file.

.EXAMPLE
  .\build.ps1
  .\build.ps1 -SmokeTest
#>
param(
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot 'venv'
$pythonExe = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
    Write-Host "[build] Creating virtual environment in $venvPath" -ForegroundColor Cyan
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
}

Write-Host "[build] Upgrading pip" -ForegroundColor Cyan
& $pythonExe -m pip install --upgrade pip | Out-Host

Write-Host "[build] Installing dependencies" -ForegroundColor Cyan
& $pythonExe -m pip install -r requirements.txt | Out-Host

$buildDir = Join-Path $PSScriptRoot 'build'
$distExe = Join-Path $PSScriptRoot 'dist\DutchTenderScraper.exe'
if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
}
if (Test-Path $distExe) {
    Remove-Item -Force $distExe
}

Write-Host "[build] Running PyInstaller" -ForegroundColor Cyan
& $pythonExe -m PyInstaller --clean --noconfirm DutchTenderScraper.spec | Out-Host
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if (-not (Test-Path $distExe)) {
    throw "Build did not produce $distExe"
}

$size = (Get-Item $distExe).Length
$sha = Get-FileHash -Algorithm SHA256 -Path $distExe
Write-Host ""
Write-Host "[build] SUCCESS" -ForegroundColor Green
Write-Host "[build] Path:   $distExe"
Write-Host "[build] Size:   $([math]::Round($size/1MB,2)) MB"
Write-Host "[build] SHA256: $($sha.Hash)"

if ($SmokeTest) {
    Write-Host ""
    Write-Host "[build] Running smoke test" -ForegroundColor Cyan
    $smokeOutput = Join-Path $PSScriptRoot 'smoke.xlsx'
    & $distExe --days 7 --output $smokeOutput --verbose
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke test returned non-zero exit code $LASTEXITCODE"
    }
    if (-not (Test-Path $smokeOutput)) {
        throw "Smoke test did not produce $smokeOutput"
    }
    Write-Host "[build] Smoke test OK: $smokeOutput" -ForegroundColor Green
}
