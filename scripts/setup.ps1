$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo-common.ps1')
try {
    $python = Get-DemoPython
    Assert-DemoNode
    $venv = Join-Path $script:Repo '.venv'
    $localPython = Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path $localPython)) {
        Write-Host "Creating model-free Python environment at $venv"
        Invoke-DemoCommand $python @('-m', 'venv', $venv)
    }
    & $localPython -c 'import sys; print(sys.version.split()[0])' *> $null
    if ($LASTEXITCODE -ne 0) { throw "Existing $venv cannot start (its base Python may have moved). Rename that directory and rerun setup." }
    Write-Host 'Installing local M2 and model-free Python dependencies...'
    Invoke-DemoCommand $localPython @('-m', 'pip', 'install', '-e', $script:Repo)
    Write-Host 'Installing M3 frontend dependencies with npm ci...'
    Install-DemoFrontend
    Set-LiveEnvironment
    Write-Host 'Setup complete. LIVE telemetry is configured in .env.local.'
    Write-Host 'Run .\scripts\start-demo.ps1 for RECORDED ONNX REPLAY (no model or GPU).'
} catch { Write-Error "Setup failed: $_"; exit 1 }
