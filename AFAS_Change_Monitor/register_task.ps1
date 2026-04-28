# Registers a Windows Task Scheduler task that runs the AFAS Change Monitor
# in the background, weekly, even when the laptop is asleep or you are not
# actively logged in to the GUI.
#
# Usage (PowerShell, in the AFAS_Change_Monitor folder):
#     .\register_task.ps1
#
# Optional parameters:
#     .\register_task.ps1 -Day Wednesday -Time "08:30"
#
# To remove the task afterwards:
#     Unregister-ScheduledTask -TaskName "AFAS Change Monitor" -Confirm:$false

param(
    [ValidateSet("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [string]$Day = "Monday",

    [string]$Time = "10:00",

    [string]$TaskName = "AFAS Change Monitor"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

$exe    = Join-Path $scriptDir "dist\AFAS Monitor.exe"
$mainPy = Join-Path $scriptDir "main.py"

if (Test-Path $exe) {
    Write-Host "Using built executable: $exe"
    $action = New-ScheduledTaskAction `
        -Execute $exe `
        -Argument "--run-once" `
        -WorkingDirectory $scriptDir
} elseif (Test-Path $mainPy) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        throw "Python not found in PATH. Install Python or build the .exe via build.bat first."
    }
    Write-Host "Using Python: $python (running main.py)"
    $action = New-ScheduledTaskAction `
        -Execute $python `
        -Argument "main.py --run-once" `
        -WorkingDirectory $scriptDir
} else {
    throw "Neither '$exe' nor '$mainPy' found. Run this script from the AFAS_Change_Monitor folder."
}

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time

# Wake the computer to run, start when available if a previous run was missed,
# and cap the run at 4 hours so a stuck scan can't block forever.
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

# Run as the current user, only when logged on (no password required).
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' registered:"
Write-Host "  Frequency  : every $Day at $Time"
Write-Host "  Working dir: $scriptDir"
Write-Host ""
Write-Host "View or edit in Task Scheduler (taskschd.msc) or run:"
Write-Host "    Get-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To trigger a manual run right now:"
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
