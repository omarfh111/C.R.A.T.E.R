$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo-common.ps1')
$frontend = $null
try {
    $python = Join-Path $script:Repo '.venv/Scripts/python.exe'
    $observations = Join-Path $script:Repo 'examples/m1-onnx-calibrated/observations.jsonl'
    if (-not (Test-Path $python)) { throw 'Model-free environment missing. Run .\scripts\setup.ps1 first.' }
    if (-not (Test-Path $observations)) { throw 'Committed ONNX observations are missing. Restore examples/m1-onnx-calibrated/.' }
    $ports = Get-DemoPorts
    Set-LiveEnvironment
    $frontend = Start-DemoFrontend
    $url = "http://127.0.0.1:$($ports.Web)/"
    Write-Host 'RECORDED ONNX REPLAY — genuine historical predictions; no live AI inference.'
    Write-Host "M3 LIVE dashboard: $url"
    Write-Host 'Opening the dashboard; M2 will wait for a WebSocket receiver before replaying frames.'
    Start-Process $url
    $run = Join-Path $script:Repo ('outputs/demo-replay-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $run -Force | Out-Null
    $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'; $env:HF_HUB_DISABLE_TELEMETRY = '1'
    Push-Location $script:Repo
    try {
        Invoke-DemoCommand $python @('-m', 'crater_m2', '--input', $observations, '--input-ground-z', '0', '--duration', '10', '--drain', '60', '--fps', '10', '--bandwidth', '4096', '--latency', '.005', '--jitter', '0', '--loss', '.25', '--blackout', '.5:5', '--queue', '128', '--attempts', '20', '--seed', '7', '--port', "$($ports.Ws)", '--wait-for-client', '120', '--report', (Join-Path $run 'm2-report.json'), '--received-jsonl', (Join-Path $run 'm2-received.jsonl'))
    } finally { Pop-Location }
    $report = Get-Content (Join-Path $run 'm2-report.json') -Raw | ConvertFrom-Json
    $source = @(Get-Content $observations | ForEach-Object { $_ | ConvertFrom-Json })
    $received = @(Get-Content (Join-Path $run 'm2-received.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
    if (-not $report.completed -or $source.Count -ne 30 -or $report.transport.generated -ne 30 -or $report.transport.delivered -ne 30 -or $received.Count -ne 30) { throw 'M2 did not deliver all 30 recorded frames. Inspect the report in the run directory.' }
    for ($i = 0; $i -lt 30; $i++) {
        if ($source[$i].capturedAt -ne $received[$i].capturedAt) { throw "Historical capture time changed at frame $i." }
    }
    Write-Host "Replay complete. Historical capture timestamps were preserved. Report: $run"
    Write-Host 'M2 delivered 30/30. Confirm M3 shows ACCEPTED 30 in the browser.'
} catch { Write-Error "Demo failed: $_"; exit 1 }
finally { Stop-DemoFrontend $frontend }
