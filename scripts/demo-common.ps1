$ErrorActionPreference = 'Stop'
$script:Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-DemoPython {
    $candidates = @()
    if ($env:CRATER_PYTHON) { $candidates += ,@($env:CRATER_PYTHON) }
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += ,@('py', '-3') }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += ,@('python') }
    foreach ($candidate in $candidates) {
        try {
            $info = & $candidate[0] @($candidate | Select-Object -Skip 1) -c 'import json,sys; print(json.dumps([sys.executable,*sys.version_info[:2]]))' 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $parsed = $info | ConvertFrom-Json
            if ([int]$parsed[1] -gt 3 -or ([int]$parsed[1] -eq 3 -and [int]$parsed[2] -ge 12)) { return [string]$parsed[0] }
        } catch { continue }
    }
    throw 'Python 3.12+ is required. Install it from python.org, or set CRATER_PYTHON to its python.exe path.'
}

function Assert-DemoNode {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 24+ is required. Install Node.js 24 and reopen PowerShell.' }
    $version = & node --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v(\d+)\.') { throw 'Cannot determine Node.js version.' }
    if ([int]$Matches[1] -lt 24) { throw "Node.js 24+ is required; found $version." }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'npm is required; reinstall Node.js with npm included.' }
}

function Invoke-DemoCommand([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE. See the error above." }
}

function Install-DemoFrontend {
    $previous = $env:NODE_USE_SYSTEM_CA
    try {
        # Node 24 can use the Windows trust store while keeping TLS verification on.
        $env:NODE_USE_SYSTEM_CA = '1'
        Push-Location $script:Repo
        try { Invoke-DemoCommand 'npm.cmd' @('ci') } finally { Pop-Location }
    } finally { $env:NODE_USE_SYSTEM_CA = $previous }
}

function Set-LiveEnvironment {
    $path = Join-Path $script:Repo '.env.local'
    $lines = if (Test-Path -LiteralPath $path) { @([IO.File]::ReadAllLines($path)) } else { @() }
    foreach ($setting in @(@('VITE_TELEMETRY_MODE', 'LIVE'), @('VITE_TELEMETRY_WS_URL', 'ws://127.0.0.1:8765/telemetry'))) {
        $key, $value = $setting
        $matches = @($lines | Where-Object { $_ -match "^\s*$key\s*=" })
        if ($matches.Count -eq 0) { $lines += "$key=$value" }
        else {
            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i] -match "^\s*$key\s*=") { $lines[$i] = "$key=$value" }
            }
        }
    }
    [IO.File]::WriteAllText($path, (($lines -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
}

function Assert-DemoPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $attempt = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($attempt.AsyncWaitHandle.WaitOne(300)) {
            try { $client.EndConnect($attempt); throw "Port $Port is already occupied. Stop the existing application before starting this demo." }
            catch [Net.Sockets.SocketException] { }
        }
    } finally { $client.Dispose() }
}

function Start-DemoFrontend {
    Assert-DemoNode
    if (-not (Test-Path (Join-Path $script:Repo 'node_modules/vite/bin/vite.js'))) { throw 'Frontend packages missing. Run the matching setup script first.' }
    Assert-DemoPort 5173
    Assert-DemoPort 8765
    $vite = Join-Path $script:Repo 'node_modules/vite/bin/vite.js'
    $process = Start-Process -FilePath (Get-Command node).Source -ArgumentList @("`"$vite`"", '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $script:Repo -PassThru -WindowStyle Hidden
    for ($i = 0; $i -lt 100; $i++) {
        if ($process.HasExited) { throw "M3 exited during startup (code $($process.ExitCode)). Run npm run dev for details." }
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $attempt = $client.BeginConnect('127.0.0.1', 5173, $null, $null)
            if ($attempt.AsyncWaitHandle.WaitOne(200)) {
                try { $client.EndConnect($attempt); return $process }
                catch [Net.Sockets.SocketException] { }
            }
        } finally { $client.Dispose() }
        Start-Sleep -Milliseconds 100
    }
    Stop-DemoFrontend $process
    throw 'M3 did not become ready at http://127.0.0.1:5173/ within 30 seconds.'
}

function Stop-DemoFrontend($Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F *> $null
        $Process.WaitForExit(5000) | Out-Null
    }
}
