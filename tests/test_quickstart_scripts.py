"""Windows setup regression checks for judge-facing launchers."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL, reason="Windows PowerShell required")


def run_ps(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([POWERSHELL, "-NoProfile", "-Command", code], text=True, capture_output=True, timeout=30)


def quote_ps(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def test_scripts_parse_without_errors():
    files = ["demo-common.ps1", "setup.ps1", "start-demo.ps1", "setup-gpu.ps1", "start-live.ps1"]
    for name in files:
        code = (
            "$errors=$null; "
            f"[Management.Automation.Language.Parser]::ParseFile({quote_ps(SCRIPTS / name)},"
            "[ref]$null,[ref]$errors)|Out-Null; if($errors){throw $errors}"
        )
        result = run_ps(code)
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_live_env_preserves_other_values_and_is_repeatable(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("OTHER_SETTING=preserve\nVITE_TELEMETRY_MODE=MOCK\n", encoding="utf-8")
    code = (
        f". {quote_ps(SCRIPTS / 'demo-common.ps1')}; "
        f"$script:Repo={quote_ps(tmp_path)}; "
        "$env:CRATER_DEMO_WEB_PORT='5174'; $env:CRATER_DEMO_WS_PORT='8766'; "
        "Set-LiveEnvironment; Set-LiveEnvironment"
    )
    result = run_ps(code)
    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8").splitlines() == [
        "OTHER_SETTING=preserve",
        "VITE_TELEMETRY_MODE=LIVE",
        "VITE_TELEMETRY_WS_URL=ws://127.0.0.1:8766/telemetry",
    ]


def test_port_override_validation():
    code = (
        f". {quote_ps(SCRIPTS / 'demo-common.ps1')}; "
        "$env:CRATER_DEMO_WEB_PORT='70000'; $env:CRATER_DEMO_WS_PORT='8766'; Get-DemoPorts"
    )
    result = run_ps(code)
    assert result.returncode != 0
    assert "1024 to 65535" in result.stderr
