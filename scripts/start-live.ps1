$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo-common.ps1')
$frontend = $null
$previousWebPort = $env:CRATER_DEMO_WEB_PORT
$previousWsPort = $env:CRATER_DEMO_WS_PORT
try {
    $python = Join-Path $script:Repo '.venv-gpu/Scripts/python.exe'
    $bundle = Join-Path $script:Repo 'examples/m1-onnx-calibrated'
    $cache = Join-Path $script:Repo '.cache/huggingface'
    if (-not (Test-Path $python)) { throw 'DirectML environment missing. Run .\scripts\setup-gpu.ps1 first.' }
    foreach ($file in @('scene.mp4', 'calibration.json')) {
        if (-not (Test-Path (Join-Path $bundle $file))) { throw "Committed $file is missing from $bundle." }
    }
    $expected = '74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9'
    if ((Get-FileHash (Join-Path $bundle 'scene.mp4') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Calibrated source video SHA-256 mismatch.' }
    $offline = 'from crater_m1.onnx_prepare import prepare; from crater_m1.windows_gpu import adapters,preferred_adapter; import onnxruntime as ort,sys; assert "DmlExecutionProvider" in ort.get_available_providers(); print("DirectML GPU:",preferred_adapter(adapters())); print("Pinned model:",prepare(sys.argv[1],download=False)[1])'
    Invoke-DemoCommand $python @('-c', $offline, $cache)
    $ports = Initialize-DemoRunPorts
    Set-LiveEnvironment
    $frontend = Start-DemoFrontend
    $url = "http://127.0.0.1:$($ports.Web)/"
    Write-Host 'FULL LIVE AI — pixel-derived Grounding DINO Tiny ONNX through DirectML.'
    Write-Host "M3 LIVE dashboard: $url"
    Write-Host 'Opening dashboard; M2 waits for its WebSocket connection before capture.'
    Start-Process $url
    $run = Join-Path $script:Repo ('outputs/demo-live-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $run -Force | Out-Null
    $env:CRATER_M2_SOURCE = $script:Repo
    $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'; $env:HF_HUB_DISABLE_TELEMETRY = '1'
    Push-Location $script:Repo
    try {
        Invoke-DemoCommand $python @('-m', 'crater_m2', '--perception-video', (Join-Path $bundle 'scene.mp4'), '--calibration', (Join-Path $bundle 'calibration.json'), '--perception-backend', 'onnx-grounding-dino', '--device', 'directml', '--cache-dir', $cache, '--perception-output', (Join-Path $run 'perception'), '--perception-buffer', '4', '--no-preview', '--duration', '300', '--drain', '120', '--fps', '10', '--bandwidth', '4096', '--latency', '.005', '--jitter', '0', '--loss', '.25', '--no-blackout', '--queue', '128', '--attempts', '20', '--seed', '7', '--port', "$($ports.Ws)", '--wait-for-client', '120', '--report', (Join-Path $run 'm2-report.json'), '--received-jsonl', (Join-Path $run 'm2-received.jsonl'))
    } finally { Pop-Location }
    $report = Get-Content (Join-Path $run 'm2-report.json') -Raw | ConvertFrom-Json
    if (-not $report.completed -or $report.transport.generated -ne 30 -or $report.transport.delivered -ne 30 -or $report.source.producerCompleted -ne $true) { throw "Live inference or transport was incomplete. Inspect $run." }
    Write-Host "Live ONNX inference and M2 delivery complete: 30/30. Report: $run"
    Write-Host 'Confirm M3 shows ACCEPTED 30 in the browser.'
} catch { Write-Error "Live demo failed: $_"; exit 1 }
finally {
    Stop-DemoFrontend $frontend
    $env:CRATER_DEMO_WEB_PORT = $previousWebPort
    $env:CRATER_DEMO_WS_PORT = $previousWsPort
}
