param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Resolve-Python {
    param([string]$Requested)
    $Candidates = @()
    if ($Requested) { $Candidates += $Requested }
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) { $Candidates += $PythonCommand.Source }
    $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $Candidates += $CodexPython
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate)) { return $Candidate }
    }
    throw "Python 3.10+ was not found. Pass its path with -PythonPath."
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $BasePython = Resolve-Python -Requested $PythonPath
    & $BasePython -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")

$NpmCommand = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NpmCommand) { throw "Node.js/npm was not found. Install Node.js 18+ and retry." }
Push-Location (Join-Path $ProjectRoot "frontend")
try {
    & $NpmCommand.Source install --no-audit --no-fund
    & $NpmCommand.Source run build
}
finally {
    Pop-Location
}

Write-Host "BADIA AI setup is complete." -ForegroundColor Green
