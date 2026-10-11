"""Real Windows PowerShell process lifecycle checks; no Ollama or GPU needed."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher lifecycle")
def test_startup_monitor_kills_only_owned_tree_and_preserves_utf8(tmp_path):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell 5.1 is not installed")
    launcher = Path(__file__).resolve().parents[1] / "scripts/start-assistant.ps1"
    harness = tmp_path / "verify launcher.ps1"
    harness.write_text(r'''
param([string]$LauncherPath, [string]$PythonPath)
$ErrorActionPreference = 'Stop'
$taskErrors = $null
$taskTokens = $null
$taskAst = [Management.Automation.Language.Parser]::ParseFile($LauncherPath, [ref]$taskTokens, [ref]$taskErrors)
if ($taskErrors.Count) { throw 'Launcher parse failed.' }
foreach ($taskName in @('Start-AssistantChild', 'Stop-AssistantOwnedTree', 'Invoke-AssistantCli')) {
    $taskFunction = $taskAst.FindAll({ param($taskNode) $taskNode -is [Management.Automation.Language.FunctionDefinitionAst] -and $taskNode.Name -eq $taskName }, $true) | Select-Object -First 1
    Invoke-Expression $taskFunction.Extent.Text
}
$assistantRepo = $PSScriptRoot
$assistantRun = $PSScriptRoot
$ownedOllamaProcess = $null
$script:assistantCliStage = 0
$taskPreviousUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
$taskPidFile = Join-Path $PSScriptRoot 'child.pid'
$taskPythonFile = Join-Path $PSScriptRoot 'owned child.py'
$taskCode = "import pathlib, subprocess, sys, time`nchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])`npathlib.Path(__file__).with_name('child.pid').write_text(str(child.pid))`nprint('dummy child ready', flush=True)`ntime.sleep(60)`n"
[IO.File]::WriteAllText($taskPythonFile, $taskCode, [Text.UTF8Encoding]::new($false))
function Assert-AssistantNoCapture {
    if (Test-Path -LiteralPath $taskPidFile) { throw 'simulated live capture appeared' }
}
$taskAborted = $false
try { Invoke-AssistantCli @($taskPythonFile) | Out-Null }
catch { if ([string]$_ -notmatch 'simulated live capture') { throw }; $taskAborted = $true }
if (-not $taskAborted) { throw 'Startup monitor did not abort.' }
$taskChildPid = [int]([IO.File]::ReadAllText($taskPidFile))
if (Get-Process -Id $taskChildPid -ErrorAction SilentlyContinue) { throw "Owned descendant $taskChildPid survived cleanup." }
function Assert-AssistantNoCapture { }
$taskUnicodeFile = Join-Path $PSScriptRoot 'unicode output.py'
[IO.File]::WriteAllText($taskUnicodeFile, 'import json; print(json.dumps({"answer": "st\u00e9r\u00e9o"}, ensure_ascii=False))', [Text.UTF8Encoding]::new($false))
$taskOutput = Invoke-AssistantCli @($taskUnicodeFile)
if (($taskOutput | ConvertFrom-Json).answer -cne "st$([char]0xE9)r$([char]0xE9)o") { throw 'UTF-8 stdout did not round trip.' }
if ([Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process') -cne $taskPreviousUtf8) { throw 'Child environment leaked into the launcher.' }
Write-Host 'OWNED_TREE_AND_UTF8_PASSED'
''', encoding="utf-8")
    process = subprocess.Popen(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness),
         "-LauncherPath", str(launcher), "-PythonPath", sys.executable],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            # This process and its descendants belong to this test invocation.
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=5)
    assert process.returncode == 0, (stdout + stderr).decode("utf-8", errors="replace")
    assert b"OWNED_TREE_AND_UTF8_PASSED" in stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell command-line parsing")
def test_capture_guard_recognizes_invocation_without_blocking_source_inspection(tmp_path):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell 5.1 is not installed")
    launcher = Path(__file__).resolve().parents[1] / "scripts/start-assistant.ps1"
    cases = [
        (["powershell.exe", "-NoProfile", "-File", r"D:\repo with spaces\scripts\start-live.ps1"], True),
        (["pwsh.exe", "-Command", "& 'D:/repo with spaces/scripts/start-live.ps1' -Video scene.mp4"], True),
        (["powershell.exe", "-Command", r".\scripts\start-live.ps1"], True),
        (["powershell.exe", "-Command", "Get-Content -LiteralPath 'D:/repo/scripts/start-live.ps1'"], False),
        (["powershell.exe", "-Command", "rg -n 'start-live.ps1' scripts"], False),
        (["powershell.exe", "-Command", "$source = 'D:/scripts/start-live.ps1'; Write-Output $source"], False),
        (["powershell.exe", "-Command", "Write-Output '-File D:/scripts/start-live.ps1'"], False),
        (["powershell.exe", "-Command", "function Sample { & 'D:/scripts/start-live.ps1' }; Get-Content scripts/start-assistant.ps1"], False),
        (["powershell.exe", "-Command", "python -c \"print('start-live.ps1')\""], False),
        (["powershell.exe", "-File", r"D:\scripts\other.ps1", "-Pattern", "start-live.ps1"], False),
    ]
    cases_path = tmp_path / "guard cases.json"
    cases_path.write_text(json.dumps([
        {"commandLine": subprocess.list2cmdline(arguments), "blocked": blocked}
        for arguments, blocked in cases
    ]), encoding="utf-8")
    harness = tmp_path / "guard check.ps1"
    harness.write_text(r'''
param([string]$LauncherPath, [string]$CasesPath)
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($LauncherPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Launcher parse failed.' }
foreach ($name in @('Get-AssistantCommandLineArguments', 'Test-AssistantLivePowerShellCommand', 'Get-AssistantLiveCapture')) {
    $function = $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true) | Select-Object -First 1
    Invoke-Expression $function.Extent.Text
}
$cases = Get-Content -LiteralPath $CasesPath -Raw | ConvertFrom-Json
foreach ($case in $cases) {
    $actual = Test-AssistantLivePowerShellCommand $case.commandLine
    if ($actual -ne $case.blocked) { throw "Unexpected guard decision $actual for $($case.commandLine)" }
    $script:guardProcess = [pscustomobject]@{ Name = 'powershell.exe'; CommandLine = $case.commandLine; ProcessId = 123 }
    function Get-CimInstance { param([string]$ClassName) return $script:guardProcess }
    $found = Get-AssistantLiveCapture
    if (($null -ne $found) -ne $case.blocked) { throw "Process guard disagreed for $($case.commandLine)" }
}
Write-Host 'CAPTURE_INVOCATION_GUARD_PASSED'
''', encoding="utf-8")
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness),
         "-LauncherPath", str(launcher), "-CasesPath", str(cases_path)],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
    )
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert b"CAPTURE_INVOCATION_GUARD_PASSED" in result.stdout
