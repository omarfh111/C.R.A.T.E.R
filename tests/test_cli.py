import json
import subprocess
import sys
import asyncio
from crater_m2.__main__ import arguments, run_mission
from crater_m2.source import Scenario
from datetime import datetime, timezone
from copy import deepcopy
import pytest
from crater_m2.source import observation_to_frame
from crater_m2.codec import encode_frame


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


def test_rejected_details_are_sampled_but_totals_remain_complete(tmp_path):
    observation = Scenario(datetime.now(timezone.utc)).observation(0)
    observation["detections"] = [dict(id="bad", type="rock", contactPixel=[-1, 0], confidence=.9)]
    source = tmp_path / "source.jsonl"
    source.write_text((json.dumps(observation) + "\n") * 200, encoding="utf-8")
    args = arguments(["--benchmark", "--input", str(source), "--duration", "21", "--fps", "10",
                      "--bandwidth", "10000", "--latency", "0", "--jitter", "0", "--loss", "0", "--no-blackout",
                      "--rejection-samples", "3", "--link-history", "4",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])
    report = asyncio.run(run_mission(args))
    assert report["completed"]
    assert report["source"]["rejectedDetections"] == 200
    assert len(report["rejectedDetections"]) == 3
    assert report["rejectedDetectionsOmitted"] == 197
    assert report["transport"]["delivered"] == 200


def test_failed_enqueue_does_not_inflate_partial_report_byte_averages(tmp_path):
    first = Scenario(datetime.now(timezone.utc)).observation(0)
    second = deepcopy(first)
    second["roverId"] = "different-rover"
    source = tmp_path / "source.jsonl"
    source.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    args = arguments(["--benchmark", "--input", str(source), "--duration", "3", "--no-blackout", "--loss", "0",
                      "--report", str(tmp_path / "report.json"), "--received-jsonl", str(tmp_path / "received.jsonl")])
    with pytest.raises(ValueError, match="one rover"):
        asyncio.run(run_mission(args))
    report = json.loads((tmp_path / "report.json").read_text())
    expected = observation_to_frame(first, 0, dict(status="connected", packetsSent=0, packetsLost=0)).frame
    assert report["transport"]["generated"] == 1
    assert report["meanBinaryFrameBytes"] == len(encode_frame(expected))
    assert report["meanJsonFrameBytes"] == len(json.dumps(expected, separators=(",", ":")).encode())
    assert not report["completed"]
