$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir = Join-Path $ProjectRoot ".run"
$Ports = @{ demo = 4173; legacy_api = 8000 }

foreach ($Name in @("backend", "frontend")) {
    $PidPath = Join-Path $RunDir "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidPath)) { continue }
    $ProcessId = 0
    if ([int]::TryParse((Get-Content -Raw -LiteralPath $PidPath).Trim(), [ref]$ProcessId)) {
        $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($Process) { Stop-Process -Id $ProcessId -Force }
    }
    Remove-Item -LiteralPath $PidPath -ErrorAction SilentlyContinue
}

# A Windows virtual-environment launcher can leave its interpreter child alive.
# Resolve only the two known local demo ports and stop their exact listener PIDs.
Start-Sleep -Milliseconds 250
foreach ($Port in $Ports.Values) {
    $Pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+.*LISTENING\s+(\d+)\s*$"
    foreach ($Line in (& netstat.exe -ano -p tcp)) {
        $Match = [regex]::Match($Line, $Pattern)
        if ($Match.Success) {
            $ListenerPid = [int]$Match.Groups[1].Value
            Stop-Process -Id $ListenerPid -Force -ErrorAction SilentlyContinue
        }
    }
}
Write-Host "BADIA AI demo processes stopped." -ForegroundColor Green
