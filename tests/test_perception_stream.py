import asyncio
import json
import threading
import subprocess
import sys
import time
from datetime import datetime, timezone

import pytest
from websockets.asyncio.client import connect

from crater_m1.detectors import SyntheticContrastDetector
from crater_m1.simulation import generate
from crater_m2.__main__ import arguments, execute, run_mission
from crater_m2.bridge import TelemetryBridge
from crater_m2.perception import PerceptionStream
from crater_m2.source import Scenario


def test_callback_handoff_is_bounded_and_shutdown_unblocks_producer():
    async def check():
        first = threading.Event()

        def producer(callback):
            for number in range(100):
                callback({"number": number})
                first.set()

        async with PerceptionStream(producer, capacity=1) as stream:
            assert await asyncio.to_thread(first.wait, 2)
            assert stream.buffered == 1
            assert stream.poll() == {"number": 0}
        assert not stream.thread.is_alive()
        assert stream.interrupted

    asyncio.run(check())


def test_producer_errors_reach_consumer():
    async def check():
        def producer(callback):
            raise ValueError("calibration missing for frame 7")

        with pytest.raises(ValueError, match="frame 7"):
            async with PerceptionStream(producer) as stream:
                await asyncio.to_thread(stream.thread.join, 2)
                stream.poll()

    asyncio.run(check())


def test_actual_m1_callback_reaches_m3_socket_without_jsonl_replay(tmp_path):
    from crater_m1.pipeline import run

    generate(tmp_path / "scene", count=6)
    args = arguments(["--duration", "3", "--drain", "4", "--fps", "10",
                      "--bandwidth", "4096", "--latency", ".005", "--jitter", "0",
                      "--loss", ".2", "--blackout", ".2:.4", "--port", "0",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])

    def producer(callback):
        return run(tmp_path / "scene/scene.mp4", tmp_path / "m1-run",
                   SyntheticContrastDetector(), calibration=tmp_path / "scene/calibration.json",
                   preview=False, on_observation=callback)

    async def check():
        async with TelemetryBridge(port=0) as bridge:
            async with connect(bridge.url) as client:
                async with PerceptionStream(producer, capacity=2) as stream:
                    task = asyncio.create_task(run_mission(args, bridge, stream=stream))
                    try:
                        received = [json.loads(await asyncio.wait_for(client.recv(), 8)) for _ in range(6)]
                        report = await task
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                assert [item["sequence"] for item in received] == list(range(6))
                assert all(len(item["hazards"]) == 3 for item in received)
                assert len({hazard["id"] for item in received for hazard in item["hazards"]}) == 3
                assert report["completed"]
                assert report["transport"]["acknowledged"] == 6
                assert report["source"]["source"] == "m1-live-callback"
                assert report["transport"]["dataPacketsLost"] > 0
                saved = [json.loads(line) for line in (tmp_path / "m1-run/observations.jsonl").read_text().splitlines()]
                assert [item["capturedAt"] for item in received] == [item["capturedAt"] for item in saved]

    asyncio.run(check())


def test_live_perception_requires_calibration_and_rejects_virtual_time(tmp_path):
    with pytest.raises(SystemExit):
        arguments(["--perception-video", "video.mp4"])
    with pytest.raises(SystemExit):
        arguments(["--perception-video", "video.mp4", "--calibration", "pose.json", "--benchmark"])


def test_cli_uses_local_m1_stream_and_preserves_input_files(tmp_path):
    generate(tmp_path / "scene", count=3)
    calibration = tmp_path / "scene/calibration.json"
    initial_calibration = calibration.read_bytes()
    base = ["--perception-video", str(tmp_path / "scene/scene.mp4"),
            "--calibration", str(calibration), "--perception-backend", "synthetic-contrast",
            "--perception-output", str(tmp_path / "m1"), "--no-preview", "--port", "0",
            "--duration", "3", "--drain", "3", "--fps", "10", "--bandwidth", "4096",
            "--loss", "0", "--no-blackout", "--report", str(tmp_path / "report.json"),
            "--received-jsonl", str(tmp_path / "received.jsonl")]
    with pytest.raises(SystemExit):
        arguments(base + ["--report", str(calibration)])
    with pytest.raises(SystemExit):
        arguments(base + ["--report", str(tmp_path / "m1/observations.jsonl")])
    result = subprocess.run([sys.executable, "-m", "crater_m2", *base],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["source"]["source"] == "m1-live-callback"
    assert report["transport"]["acknowledged"] == 3
    assert calibration.read_bytes() == initial_calibration


def test_shutdown_propagates_errors_not_yet_polled():
    async def check():
        def producer(callback):
            raise ValueError("late inference failure")

        with pytest.raises(ValueError, match="late inference failure"):
            async with PerceptionStream(producer) as stream:
                await asyncio.to_thread(stream.thread.join, 2)

    asyncio.run(check())


def test_delayed_inference_keeps_link_snapshot_at_capture(tmp_path):
    args = arguments(["--duration", "2", "--drain", "2", "--fps", "20",
                      "--bandwidth", "4096", "--latency", ".005", "--jitter", "0",
                      "--loss", "0", "--blackout", ".3:.6",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])

    def producer(callback):
        observation = Scenario(datetime.now(timezone.utc)).observation(0)
        callback(observation)
        # Both images captured before any radio send, but inference finishes later.
        time.sleep(.4)
        callback(observation)

    async def check():
        async with PerceptionStream(producer) as stream:
            report = await run_mission(args, stream=stream)
        received = [json.loads(line) for line in (tmp_path / "received.jsonl").read_text().splitlines()]
        assert len(received) == 2 and report["completed"]
        assert all(item["link"] == {"status": "connected", "packetsSent": 0, "packetsLost": 0} for item in received)
        assert report["transport"]["dataPacketsSent"] == 2

    asyncio.run(check())


def test_late_failure_marks_saved_report_incomplete(tmp_path, monkeypatch):
    generate(tmp_path / "scene", count=2)
    args = arguments(["--perception-video", str(tmp_path / "scene/scene.mp4"),
                      "--calibration", str(tmp_path / "scene/calibration.json"),
                      "--perception-output", str(tmp_path / "m1"), "--port", "0",
                      "--duration", ".1", "--drain", "0",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])

    def producer(callback):
        time.sleep(.3)
        raise ValueError("late failure beyond mission duration")

    monkeypatch.setattr("crater_m2.perception.local_producer", lambda args: producer)
    with pytest.raises(ValueError, match="late failure"):
        asyncio.run(execute(args))
    report = json.loads((tmp_path / "report.json").read_text())
    assert not report["completed"]
    assert "late failure" in report["source"]["error"]


def test_no_observations_before_deadline_is_not_success(tmp_path):
    args = arguments(["--duration", ".1", "--drain", "0",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])

    def producer(callback):
        time.sleep(.2)
        callback(Scenario(datetime.now(timezone.utc)).observation(0))

    async def check():
        async with PerceptionStream(producer) as stream:
            report = await run_mission(args, stream=stream)
        assert not report["completed"]
        assert report["transport"]["generated"] == 0

    asyncio.run(check())


def test_live_clock_reaches_duration_boundary_without_extra_drain(tmp_path):
    args = arguments(["--duration", ".1", "--drain", "0", "--bandwidth", "10000",
                      "--latency", "0", "--jitter", "0", "--loss", "0", "--no-blackout",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])
    report = asyncio.run(run_mission(args))
    assert report["completed"] and report["simulatedElapsedS"] >= .1
