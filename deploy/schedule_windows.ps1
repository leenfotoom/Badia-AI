# Registers the BADIA daily update (every 6 h) and weekly gated retrain check.
# The CLI holds one shared operation lock across update/acquire/train/retrain, so
# the two differently named tasks cannot mutate daily artifacts concurrently.
# Run once as the same Windows user that owns the project checkout.
[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

function Resolve-PythonRuntime {
    param([string]$Requested)

    $candidates = @()
    if ($Requested) { $candidates += $Requested }
    $candidates += $venvPython

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }

    $systemPython = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
    if ($systemPython) { return $systemPython.Source }
    throw "No Python runtime was found. Run .\setup_demo.ps1 first, or pass -PythonPath with an absolute python.exe path."
}

$py = Resolve-PythonRuntime -Requested $PythonPath
$dailyData = Join-Path $root "data\daily"
New-Item -ItemType Directory -Force -Path $dailyData | Out-Null

# Importing the CLI catches a missing/broken environment now instead of creating tasks
# that fail later without a useful Task Scheduler message.
Push-Location $root
try {
    $cliHelp = (& $py -m backend.app.daily.cli --help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "The selected Python runtime cannot import BADIA's daily dependencies. Run .\setup_demo.ps1 or select the correct -PythonPath."
    }
    foreach ($requiredCommand in @("acquire", "train-local", "update", "retrain")) {
        if ($cliHelp -notmatch [regex]::Escape($requiredCommand)) {
            throw "The BADIA daily CLI does not expose required command '$requiredCommand'."
        }
    }
}
finally {
    Pop-Location
}

$firstUpdate = (Get-Date).AddMinutes(5)
$taskCommands = @(
    "New-ScheduledTaskAction",
    "New-ScheduledTaskTrigger",
    "New-ScheduledTaskSettingsSet",
    "Register-ScheduledTask"
)
foreach ($commandName in $taskCommands) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Windows Scheduled Tasks command '$commandName' is unavailable on this host."
    }
}

if ($ValidateOnly) {
    Write-Host "Validation passed; no tasks were registered."
    Write-Host "Project: $root"
    Write-Host "Python:  $py"
    Write-Host "Update:  every 6 hours, first run $($firstUpdate.ToString('s'))"
    Write-Host "Retrain: Sunday at 03:40 local time (local cadence check runs before any download)"
    Write-Host "Lock:    one shared daily-operation lock prevents cross-task overlap"
    Write-Host "Failure: provider fallback/unavailable exits nonzero so Task Scheduler can retry"
    exit 0
}

$upd = New-ScheduledTaskAction -Execute $py -Argument "-u -m backend.app.daily.cli update" -WorkingDirectory $root
$ret = New-ScheduledTaskAction -Execute $py -Argument "-u -m backend.app.daily.cli retrain" -WorkingDirectory $root
$every6h = New-ScheduledTaskTrigger -Once -At $firstUpdate -RepetitionInterval (New-TimeSpan -Hours 6)
$weekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:40am
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

Register-ScheduledTask -TaskName "BADIA-Daily-Update" -Description "Refresh BADIA's real daily forecast; provider failures retain the last-good snapshot." `
    -Action $upd -Trigger $every6h -Settings $settings -Force | Out-Null
Register-ScheduledTask -TaskName "BADIA-Daily-Retrain-Check" -Description "Check cadence locally; only when due acquire verified labels, train a candidate, and apply champion gates." `
    -Action $ret -Trigger $weekly -Settings $settings -Force | Out-Null
Write-Host "Scheduled: update every 6 hours; gated retrain check Sundays at 03:40 local time."
Write-Host "The CLI shared lock prevents update and retrain from modifying daily artifacts together."
Write-Host "Operational log: $dailyData\daily.log"
