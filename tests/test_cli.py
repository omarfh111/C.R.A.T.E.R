import json
import subprocess
import sys


def test_benchmark_runs_whole_chain_and_writes_canonical_frames(tmp_path):
    report = tmp_path / "report.json"
    frames = tmp_path / "received.jsonl"
    result = subprocess.run([sys.executable, "-m", "crater_m2", "--benchmark",
                             "--duration", "5", "--fps", "2", "--blackout", "1:3", "--loss", ".3",
                             "--report", str(report), "--received-jsonl", str(frames)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    metrics = json.loads(report.read_text())
    assert metrics["transport"]["generated"] == 10
    assert metrics["transport"]["deliveryRate"] == 1
    assert metrics["transport"]["pending"] == 0
    assert metrics["source"]["evaluatedObservations"] > 0
    assert metrics["meanBinaryFrameBytes"] < metrics["meanJsonFrameBytes"]
    received = [json.loads(line) for line in frames.read_text().splitlines()]
    assert [f["sequence"] for f in received] == list(range(10))
    assert all(f["roverPosition"]["frameId"] == "LOCAL_ENU_V1" for f in received)


def test_invalid_cli_settings_fail_with_message():
    result = subprocess.run([sys.executable, "-m", "crater_m2", "--benchmark", "--fps", "0"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "fps" in result.stderr.lower()
