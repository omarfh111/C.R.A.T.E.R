$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo-common.ps1')
try {
    if ($env:OS -ne 'Windows_NT') { throw 'The DirectML demo requires Windows with a compatible GPU and driver.' }
    $python = Get-DemoPython
    Assert-DemoNode
    $cache = Join-Path $script:Repo '.cache/huggingface'
    $revision = 'ff690b0a8050566c290287545bd059350f3e9096'
    $prepared = Join-Path $cache "prepared-onnx/$revision/model_fp32.onnx"
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($script:Repo))
    $requiredGB = if (Test-Path $prepared) { 2 } else { 6 }
    if ($drive.AvailableFreeSpace -lt $requiredGB * 1GB) { throw "At least $requiredGB GB free is required on $($drive.Name) for the DirectML environment and model." }
    $venv = Join-Path $script:Repo '.venv-gpu'
    $localPython = Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path $localPython)) {
        Write-Host "Creating isolated DirectML environment at $venv"
        Invoke-DemoCommand $python @('-m', 'venv', $venv)
    }
    & $localPython -c 'import sys; print(sys.version.split()[0])' *> $null
    if ($LASTEXITCODE -ne 0) { throw "Existing $venv cannot start. Rename that directory and rerun setup." }
    Write-Host 'Installing CPU PyTorch for preprocessing, then pinned ONNX Runtime DirectML dependencies...'
    Invoke-DemoCommand $localPython @('-m', 'pip', 'install', 'torch==2.9.1', 'torchvision==0.24.1', '--index-url', 'https://download.pytorch.org/whl/cpu')
    Invoke-DemoCommand $localPython @('-m', 'pip', 'install', '-e', "$script:Repo[onnx-local]", 'truststore')
    $check = 'import onnxruntime as ort; from crater_m1.windows_gpu import adapters,preferred_adapter; p=ort.get_available_providers(); print("Providers:",p); print("Selected GPU:",preferred_adapter(adapters())); assert "DmlExecutionProvider" in p, "DirectML provider unavailable"'
    Invoke-DemoCommand $localPython @('-c', $check)
    Write-Host 'Installing M3 frontend dependencies with npm ci...'
    Install-DemoFrontend
    Set-LiveEnvironment
    Write-Host 'Checking the repository-local pinned model cache...'
    $offline = 'from crater_m1.onnx_prepare import prepare; import sys; print(prepare(sys.argv[1],download=False)[1])'
    & $localPython -c $offline $cache *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Preparing the pinned Grounding DINO Tiny ONNX model with verified HTTPS.'
        Write-Host 'First-time setup may download several gigabytes and take substantial time.'
        $download = 'import truststore,sys; truststore.inject_into_ssl(); sys.argv=["crater_m1","download-onnx-model","--cache-dir",sys.argv[1]]; from crater_m1.cli import main; main()'
        Invoke-DemoCommand $localPython @('-c', $download, $cache)
    } else { Write-Host 'Pinned prepared model is already cached; no download needed.' }
    Invoke-DemoCommand $localPython @('-c', $offline, $cache)
    Write-Host 'DirectML setup complete. Run .\scripts\start-live.ps1.'
} catch { Write-Error "DirectML setup failed: $_"; exit 1 }
