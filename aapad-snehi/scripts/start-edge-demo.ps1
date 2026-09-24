$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$webRoot = Join-Path $projectRoot "web"
$env:AAPAD_ENABLE_LIVE_ADAPTERS = "false"
$env:AAPAD_EDGE_MQTT_ENABLED = "false"

$backend = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--host", "127.0.0.1" -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru

$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 | Out-Null
        $healthy = $true
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $healthy) {
    Stop-Process -Id $backend.Id, $frontend.Id -ErrorAction SilentlyContinue
    throw "Backend did not become healthy. Install dependencies first."
}

$body = @{ scenario = "flood-gradual-001"; numberOfDevices = 6; seed = 20260902; region = "visakhapatnam"; speedMultiplier = 60; timestepSeconds = 60 } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/edge/simulations" -ContentType "application/json" -Body $body
Write-Host "SIMULATED / DEMO ONLY"
Write-Host "Open http://127.0.0.1:5173/edge-early-warning"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Run: $($run.runId)"
Write-Host "Stop later with: Stop-Process -Id $($backend.Id),$($frontend.Id)"
