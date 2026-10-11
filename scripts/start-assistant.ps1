<#
.SYNOPSIS
Start optional, operator-triggered Mission Intelligence after GPU capture.
.DESCRIPTION
Uses installed models only. The original Quick Demo and both existing launchers
remain independent. Pass the exact origin printed by the dynamic demo launcher.
Ctrl+C releases only this launcher's sidecar and, if created here, its isolated
Ollama server. An existing Ollama server is never stopped or reconfigured.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DashboardOrigin,
    [ValidateRange(1024, 65535)]
    [int]$AssistantPort = 8766,
    [ValidateRange(1024, 65535)]
    [int]$OllamaPort = 11435,
    [string]$PythonPath,
    [string]$OllamaExecutable,
    [string]$GpuUuid,
    [switch]$UseExistingOllama
)

$ErrorActionPreference = 'Stop'
$assistantRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$assistantProcess = $null
$ownedOllamaProcess = $null
$assistantExitCode = 0
$assistantBase = "http://127.0.0.1:$AssistantPort"
$ollamaBase = "http://127.0.0.1:$OllamaPort"
$assistantRun = $null
$script:assistantCliStage = 0

function Assert-AssistantOrigin {
    param([string]$Origin)
    if ($Origin -notmatch '^http://(?:127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})$') {
        throw 'DashboardOrigin must be the exact HTTP loopback origin with a port, for example http://127.0.0.1:51234 (no slash or wildcard).'
    }
    $originPort = [int]$Matches[1]
    if ($originPort -lt 1 -or $originPort -gt 65535 -or [string]$originPort -cne $Matches[1]) {
        throw 'DashboardOrigin requires one canonical port from 1 to 65535.'
    }
}

function Test-AssistantPort {
    param([int]$Port)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $attempt = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $attempt.AsyncWaitHandle.WaitOne(200)) { return $false }
        try { $client.EndConnect($attempt); return $true }
        catch [Net.Sockets.SocketException] { return $false }
    } finally { $client.Dispose() }
}

function Get-AssistantLocalJson {
    param([string]$Uri)
    $request = [Net.HttpWebRequest]::Create($Uri)
    $request.Proxy = $null
    $request.AllowAutoRedirect = $false
    $request.Timeout = 2000
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -ne 200) { throw 'Unexpected local service response.' }
        $reader = [IO.StreamReader]::new($response.GetResponseStream())
        try {
            $buffer = [char[]]::new(1048577)
            $length = 0
            while ($length -lt $buffer.Length) {
                $received = $reader.Read($buffer, $length, $buffer.Length - $length)
                if ($received -eq 0) { break }
                $length += $received
            }
            if ($length -gt 1048576) { throw 'Local service response exceeded its bound.' }
            return [string]::new($buffer, 0, $length) | ConvertFrom-Json
        } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}

function Get-AssistantCommandLineArguments {
    param([string]$CommandLine)
    # Win32_Process exposes Windows quoting, not PowerShell source tokens.
    # Decode that layer before interpreting only the -Command payload as code.
    if (-not ('CraterAssistant.CommandLineNative' -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
namespace CraterAssistant {
    public static class CommandLineNative {
        [DllImport("shell32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern IntPtr CommandLineToArgvW(string commandLine, out int count);
        [DllImport("kernel32.dll")]
        public static extern IntPtr LocalFree(IntPtr pointer);
    }
}
"@
    }
    $argumentCount = 0
    $pointer = [CraterAssistant.CommandLineNative]::CommandLineToArgvW($CommandLine, [ref]$argumentCount)
    if ($pointer -eq [IntPtr]::Zero) { throw 'Process command line could not be decoded.' }
    try {
        for ($index = 0; $index -lt $argumentCount; $index++) {
            $argumentPointer = [Runtime.InteropServices.Marshal]::ReadIntPtr($pointer, $index * [IntPtr]::Size)
            [Runtime.InteropServices.Marshal]::PtrToStringUni($argumentPointer)
        }
    } finally { [CraterAssistant.CommandLineNative]::LocalFree($pointer) | Out-Null }
}

function Test-AssistantLivePowerShellCommand {
    param([string]$CommandLine)
    if (-not $CommandLine) { return $false }
    $arguments = @(Get-AssistantCommandLineArguments $CommandLine)
    for ($index = 1; $index -lt $arguments.Count; $index++) {
        if ($arguments[$index] -imatch '^-(?:file|f)$') {
            if ($index + 1 -ge $arguments.Count) { return $false }
            return (($arguments[$index + 1] -replace '\\', '/').Split('/')[-1] -ieq 'start-live.ps1')
        }
        if ($arguments[$index] -imatch '^-(?:command|c)$') {
            if ($index + 1 -ge $arguments.Count) { return $false }
            $command = $arguments[($index + 1)..($arguments.Count - 1)] -join ' '
            $parseTokens = $null
            $parseErrors = $null
            $ast = [Management.Automation.Language.Parser]::ParseInput($command, [ref]$parseTokens, [ref]$parseErrors)
            if ($parseErrors.Count) { return $false }
            $commands = $ast.FindAll({ param($node) $node -is [Management.Automation.Language.CommandAst] }, $true)
            foreach ($invocation in $commands) {
                # Function definitions may contain sample commands without running
                # them. Strings/here-strings and Get-Content arguments are never
                # command names, so source inspection cannot inhibit the assistant.
                $ancestor = $invocation.Parent
                $definition = $false
                while ($null -ne $ancestor) {
                    if ($ancestor -is [Management.Automation.Language.FunctionDefinitionAst]) { $definition = $true; break }
                    $ancestor = $ancestor.Parent
                }
                if ($definition) { continue }
                $name = $invocation.GetCommandName()
                if ($name -and (($name -replace '\\', '/').Split('/')[-1] -ieq 'start-live.ps1')) { return $true }
            }
            return $false
        }
    }
    return $false
}

function Get-AssistantLiveCapture {
    # M1 normally executes inside the M2 process using --perception-video.
    # A historical --input replay is deliberately not considered live capture.
    $processes = Get-CimInstance Win32_Process -ErrorAction Stop
    foreach ($process in $processes) {
        $line = [string]$process.CommandLine
        if ($process.Name -match '^(?:python(?:w|[0-9.]*)?|crater-m[12])\.exe$') {
            if ($line -match '(?:-m\s+crater_m1\b|crater-m1(?:\.exe)?\b)' -or
                ($line -match '(?:-m\s+crater_m2\b|crater-m2(?:\.exe)?\b)' -and $line -match '(?:^|\s)--perception-video(?:\s|=)')) {
                return $process
            }
        }
        if ($process.Name -match '^(?:powershell|pwsh)\.exe$' -and
            (Test-AssistantLivePowerShellCommand $line)) { return $process }
    }
    return $null
}

function Assert-AssistantNoCapture {
    $capture = Get-AssistantLiveCapture
    if ($null -ne $capture) {
        throw "Live perception process $($capture.ProcessId) is active. Finish capture and close its launcher before starting optional AI. Historical replay remains supported."
    }
}

function Start-AssistantChild {
    param([string]$Executable, [string[]]$Arguments, [string]$LogName, [hashtable]$Environment = @{})
    $savedEnvironment = @{}
    try {
        foreach ($key in $Environment.Keys) {
            $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
        }
        # Start-Process joins ArgumentList on Windows; quote each validated CLI
        # argument so an otherwise valid repository path may contain spaces.
        $quotedArguments = @($Arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' })
        $childProcess = Start-Process -FilePath $Executable -ArgumentList $quotedArguments -WorkingDirectory $assistantRepo `
            -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $assistantRun "$LogName.stdout.log") `
            -RedirectStandardError (Join-Path $assistantRun "$LogName.stderr.log")
        # Windows PowerShell 5.1 otherwise loses ExitCode for redirected children.
        # Retain the native handle before polling HasExited/WaitForExit.
        $null = $childProcess.Handle
        return $childProcess
    } finally {
        foreach ($key in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
        }
    }
}

function Stop-AssistantOwnedTree {
    param([Diagnostics.Process]$Process)
    if ($null -eq $Process) { return }
    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            # Windows venv Python can be a redirector with a real Python child;
            # Ollama also owns runner children. Target only the process object
            # returned by this launcher's Start-Process, never an executable name.
            $taskKill = Join-Path $env:SystemRoot 'System32/taskkill.exe'
            & $taskKill /PID ([string]$Process.Id) /T /F *> $null
            $Process.WaitForExit(5000) | Out-Null
            if (-not $Process.HasExited) {
                [Console]::Error.WriteLine("Owned process tree $($Process.Id) could not be stopped; inspect its logs and processes.")
            }
        }
    } catch {
        [Console]::Error.WriteLine("Owned process cleanup failed for PID $($Process.Id): $_")
    }
}

function Invoke-AssistantCli {
    param([string[]]$Arguments)
    $script:assistantCliStage += 1
    $logName = 'startup-' + $script:assistantCliStage.ToString('00')
    $child = $null
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        Assert-AssistantNoCapture
        $child = Start-AssistantChild $PythonPath $Arguments $logName @{ PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8' }
        Write-Host "Owned startup stage $($script:assistantCliStage) PID: $($child.Id)."
        while (-not $child.HasExited) {
            Assert-AssistantNoCapture
            if ($timer.Elapsed.TotalSeconds -gt 200) {
                throw "Startup stage exceeded its 200-second watchdog. Inspect $assistantRun/$logName.stderr.log."
            }
            Start-Sleep -Milliseconds 250
        }
        $child.WaitForExit()
        if ($child.ExitCode -ne 0) {
            throw "Assistant startup command failed with exit code $($child.ExitCode). Inspect $assistantRun/$logName.stderr.log. No model downloads are performed."
        }
        $outputPath = Join-Path $assistantRun "$logName.stdout.log"
        if ((Get-Item -LiteralPath $outputPath).Length -gt 1048576) { throw 'Startup output exceeded its bound.' }
        return [IO.File]::ReadAllText($outputPath, [Text.Encoding]::UTF8).TrimEnd()
    } catch {
        # Release owned GPU runners first when capture appears during a stage.
        # Operator-managed existing runtimes are never passed to this helper.
        Stop-AssistantOwnedTree $ownedOllamaProcess
        throw
    } finally {
        $timer.Stop()
        Stop-AssistantOwnedTree $child
    }
}

try {
    Assert-AssistantOrigin $DashboardOrigin
    if ($env:OS -ne 'Windows_NT') { throw 'This optional GPU launcher requires Windows.' }
    if ($OllamaPort -eq 11434) { throw 'The shared/default Ollama port 11434 is never managed here. Use a separate port such as 11435.' }
    if ($AssistantPort -eq $OllamaPort) { throw 'Assistant and isolated Ollama ports must differ.' }
    if (Test-AssistantPort $AssistantPort) { throw "Assistant port $AssistantPort is occupied. Choose another -AssistantPort; no existing service will be stopped." }
    Assert-AssistantNoCapture
    if (-not $PythonPath) { $PythonPath = Join-Path $assistantRepo '.venv/Scripts/python.exe' }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw 'Model-free Python environment missing. Run .\scripts\setup.ps1 first, or pass -PythonPath for an existing compatible environment.'
    }
    $PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
    $assistantRun = Join-Path $assistantRepo ('outputs/assistant-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($assistantRun) | Out-Null

    if ($UseExistingOllama) {
        if (-not (Test-AssistantPort $OllamaPort)) { throw "No existing isolated Ollama server is listening at $ollamaBase." }
        Get-AssistantLocalJson "$ollamaBase/api/version" | Out-Null
        Write-Host "Using operator-managed Ollama at $ollamaBase; its process and configuration remain operator-owned."
    } else {
        if (Test-AssistantPort $OllamaPort) { throw "Isolated Ollama port $OllamaPort is occupied. Choose another port or explicitly pass -UseExistingOllama." }
        if (-not $OllamaExecutable) {
            $ollamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
            if ($null -ne $ollamaCommand) { $OllamaExecutable = $ollamaCommand.Source }
            else { $OllamaExecutable = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe' }
        }
        if (-not (Test-Path -LiteralPath $OllamaExecutable -PathType Leaf)) { throw 'Installed Ollama executable not found. Pass -OllamaExecutable; this script does not install software.' }
        $nvidiaCommand = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
        if ($null -eq $nvidiaCommand) { throw 'nvidia-smi.exe is required to select the NVIDIA GPU by UUID.' }
        $gpuLines = & $nvidiaCommand.Source --query-gpu=uuid,name,memory.total,memory.free --format=csv,noheader,nounits
        if ($LASTEXITCODE -ne 0) { throw 'NVIDIA GPU inventory failed.' }
        $gpus = @($gpuLines | ForEach-Object {
            $columns = @($_ -split ',' | ForEach-Object { $_.Trim() })
            if ($columns.Count -ne 4 -or $columns[0] -notmatch '^GPU-[0-9a-fA-F-]+$') { throw 'Unexpected NVIDIA GPU inventory.' }
            [pscustomobject]@{ Uuid = $columns[0]; Name = $columns[1]; TotalMiB = [int]$columns[2]; FreeMiB = [int]$columns[3] }
        })
        $selectedGpu = if ($GpuUuid) { $gpus | Where-Object { $_.Uuid -ceq $GpuUuid } | Select-Object -First 1 }
                       else { $gpus | Sort-Object FreeMiB -Descending | Select-Object -First 1 }
        if ($null -eq $selectedGpu) { throw 'Selected NVIDIA GPU UUID was not found.' }
        if ($selectedGpu.FreeMiB -lt 4096) { throw "Only $($selectedGpu.FreeMiB) MiB of NVIDIA memory is free. Close other GPU applications before loading optional AI; at least 4096 MiB is required by this launcher." }
        Write-Host "Isolated GPU: $($selectedGpu.Name), $($selectedGpu.Uuid); $($selectedGpu.FreeMiB)/$($selectedGpu.TotalMiB) MiB free."
        $ollamaEnvironment = @{
            OLLAMA_HOST = "127.0.0.1:$OllamaPort"
            # Ollama appends built-in local/app origins; this is not an exact
            # origin security boundary. Browsers connect only to the sidecar.
            OLLAMA_ORIGINS = $ollamaBase
            CUDA_VISIBLE_DEVICES = $selectedGpu.Uuid
            ROCR_VISIBLE_DEVICES = '-1'
            HIP_VISIBLE_DEVICES = '-1'
            OLLAMA_VULKAN = '0'
            OLLAMA_IGPU_ENABLE = 'false'
            OLLAMA_LLM_LIBRARY = 'cuda_v13'
            OLLAMA_NO_CLOUD = '1'
            OLLAMA_NOPRUNE = '1'
            OLLAMA_NUM_PARALLEL = '1'
            OLLAMA_MAX_LOADED_MODELS = '2'
            OLLAMA_MAX_QUEUE = '1'
            OLLAMA_FLASH_ATTENTION = '1'
        }
        $ownedOllamaProcess = Start-AssistantChild $OllamaExecutable @('serve') 'ollama' $ollamaEnvironment
        Write-Host "Owned isolated Ollama PID: $($ownedOllamaProcess.Id). Shared Ollama is untouched."
        $ollamaReady = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Assert-AssistantNoCapture
            if ($ownedOllamaProcess.HasExited) { throw "Isolated Ollama exited. Inspect $assistantRun/ollama.stderr.log." }
            try { Get-AssistantLocalJson "$ollamaBase/api/version" | Out-Null; $ollamaReady = $true; break }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ollamaReady) { throw 'Isolated Ollama did not become ready within its startup budget.' }
    }

    $common = @('-m', 'crater_assistant', '--ollama-url', $ollamaBase, '--gpu',
                '--keep-alive', '120', '--num-ctx', '4096', '--num-predict', '240')
    # First CUDA loading/kernel compilation is separately budgeted. No HTTP
    # question service is exposed until startup has finished.
    $startupArguments = $common + @('--timeout', '180')
    $serviceArguments = $common + @('--timeout', '45')
    Write-Host 'Checking installed models and preparing local AI. First CUDA compilation can take about two minutes; startup calls have a 180-second budget.'
    Push-Location $assistantRepo
    try {
        Invoke-AssistantCli ($startupArguments + @('check'))
        $manifest = Get-Content (Join-Path $assistantRepo 'docs/knowledge/corpus.json') -Raw | ConvertFrom-Json
        $sources = @($manifest.files | ForEach-Object { Join-Path $assistantRepo $_ })
        $indexPath = Join-Path $assistantRun 'research-index.json'
        Assert-AssistantNoCapture
        Invoke-AssistantCli ($startupArguments + @('index') + $sources + @('--output', $indexPath))
        Assert-AssistantNoCapture
        Invoke-AssistantCli ($startupArguments + @('warm'))
        Assert-AssistantNoCapture
        Write-Host 'Exercising retrieval and first-prompt CUDA kernels with a fixed reference question before accepting operator requests.'
        $warmupAnswer = Invoke-AssistantCli ($startupArguments + @('ask',
            'According to NASA, how do the stereo Navcams and Hazcams of Perseverance help with terrain assessment?',
            '--index', $indexPath, '--top-k', '3'))
        $warmupText = $warmupAnswer -join "`n"
        $warmupResult = $warmupText | ConvertFrom-Json
        [IO.File]::WriteAllText((Join-Path $assistantRun 'startup-answer.json'), $warmupText + "`n", [Text.UTF8Encoding]::new($false))
        if ($warmupResult.status -ne 'answered') {
            throw "The startup reference answer did not pass evidence validation. Inspect $assistantRun/startup-answer.json; no question service has started."
        }
    } finally { Pop-Location }
    $loaded = Get-AssistantLocalJson "$ollamaBase/api/ps"
    $chatModel = @($loaded.models | Where-Object { $_.name -eq 'qwen3:4b-instruct-2507-q4_K_M' -or $_.model -eq 'qwen3:4b-instruct-2507-q4_K_M' })
    if ($chatModel.Count -ne 1 -or [long]$chatModel[0].size_vram -le 0) {
        throw 'Qwen did not report GPU-resident memory. Inspect isolated Ollama logs; CPU fallback is not accepted as GPU evidence.'
    }
    Write-Host "Qwen reported GPU residency: $([math]::Round([long]$chatModel[0].size_vram / 1MB, 1)) MiB."
    Assert-AssistantNoCapture
    $assistantProcess = Start-AssistantChild $PythonPath ($serviceArguments + @('serve', '--index', $indexPath, '--port', [string]$AssistantPort,
                                                                  '--allow-origin', $DashboardOrigin, '--block-live-m1')) 'assistant' @{ PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8' }
    Write-Host "Owned assistant sidecar PID: $($assistantProcess.Id)."
    $assistantReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Assert-AssistantNoCapture
        if ($assistantProcess.HasExited) { throw "Assistant exited during startup. Inspect $assistantRun/assistant.stderr.log." }
        try { $health = Get-AssistantLocalJson "$assistantBase/health"; $assistantReady = $health.httpReady -eq $true; if ($assistantReady) { break } }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $assistantReady) { throw 'Assistant HTTP service did not become ready.' }
    Write-Host "Mission Intelligence service: $assistantBase"
    Write-Host "Allowed dashboard origin: $DashboardOrigin"
    Write-Host 'In Mission Control, open Mission Intelligence, enter the service URL, and select CONNECT LOCAL AI.'
    Write-Host 'Answers are operator-triggered, use three retrieved passages, and remain unverified scientific context.'
    Write-Host "Logs and local index: $assistantRun"
    Write-Host 'Use after GPU capture. Close this launcher with Ctrl+C before starting a new live capture.'
    if ($UseExistingOllama) { Write-Host 'Existing Ollama/model lifetime is operator-managed; this launcher stops only its own HTTP sidecar.' }
    while (-not $assistantProcess.HasExited) {
        Start-Sleep -Milliseconds 250
        $capture = Get-AssistantLiveCapture
        if ($null -ne $capture) { throw "Live perception process $($capture.ProcessId) appeared. Closing optional AI to protect capture; finish capture before restarting the assistant." }
    }
    if ($assistantProcess.ExitCode -ne 0) { throw "Assistant exited with code $($assistantProcess.ExitCode). Inspect its logs." }
} catch {
    [Console]::Error.WriteLine("Optional assistant failed: $_")
    $assistantExitCode = 1
} finally {
    # Stopping this owned server tree also stops its GPU runners immediately;
    # no unload request can queue behind a long generation during capture.
    # In UseExistingOllama mode this object is null and its server is untouched.
    Stop-AssistantOwnedTree $ownedOllamaProcess
    Stop-AssistantOwnedTree $assistantProcess
}
exit $assistantExitCode
