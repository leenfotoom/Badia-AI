$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$FrontendIndex = Join-Path $ProjectRoot "frontend\dist\index.html"
$RunDir = Join-Path $ProjectRoot ".run"

if (-not (Test-Path -LiteralPath $VenvPython) -or -not (Test-Path -LiteralPath $FrontendIndex)) {
    & (Join-Path $ProjectRoot "setup_demo.ps1")
}
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$Backend = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "4173" `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RunDir "backend.out.log") `
    -RedirectStandardError (Join-Path $RunDir "backend.err.log")

Set-Content -LiteralPath (Join-Path $RunDir "backend.pid") -Value $Backend.Id
Remove-Item -LiteralPath (Join-Path $RunDir "frontend.pid") -ErrorAction SilentlyContinue

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    try {
        $Api = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:4173/api/health" -TimeoutSec 1
        $Web = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:4173/" -TimeoutSec 1
        if ($Api.StatusCode -eq 200 -and $Web.StatusCode -eq 200) { $Ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}

if (-not $Ready) { throw "The demo did not become ready. Check .run/*.err.log." }
Write-Host "BADIA AI is ready:" -ForegroundColor Green
Write-Host "  App: http://127.0.0.1:4173/"
Write-Host "  API: http://127.0.0.1:4173/api/docs"
Write-Host "Run .\stop_demo.ps1 when finished."
