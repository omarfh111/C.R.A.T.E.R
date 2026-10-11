"""Calibrated fixture exercises transport, not learned detector accuracy."""
import asyncio
import json

import pytest


def calibrated_rows(count=12):
    rows = []
    for n in range(count):
        camera = dict(width=640, height=480, fx=400, fy=400, cx=320, cy=240,
                      centerEnuM=[n, 0, 2], rotationCameraToEnu=[[1, 0, 0], [0, -1, 0], [0, 0, -1]])
        rows.append(dict(schemaVersion=1, roverId="rover-1", capturedAt=f"2026-10-10T12:00:00.{n*10:03d}Z",
                         roverPosition=dict(frameId="LOCAL_ENU_V1", xM=n, yM=0, zM=0),
                         positionUncertaintyRadiusM=.1, camera=camera,
                         image=dict(width=640, height=480),
                         detections=[dict(id="rock-1", type="rock", contactPixel=[520, 240], confidence=.8)]))
    return rows


def test_replay_collects_every_socket_frame_through_loss_blackout_and_recovery(tmp_path):
    from crater_m2.validation import capture_pipeline
    rows = calibrated_rows()
    source = tmp_path / "observations.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    output = tmp_path / "validation"
    result = asyncio.run(capture_pipeline([
        "--input", str(source), "--duration", "4", "--drain", "8", "--fps", "10",
        "--bandwidth", "4096", "--latency", ".005", "--jitter", "0", "--loss", ".25",
        "--blackout", ".15:.8", "--queue", "32", "--seed", "7"], output))
    assert result["webSocketFrames"] == 12
    assert result["socketMatchesDecodedFrames"] is True
    report = result["m2Report"]
    assert report["completed"] and report["transport"]["acknowledged"] == 12
    assert report["transport"]["retransmissions"] > 0
    assert report["transport"]["dataPacketsLost"] > 0
    assert report["transport"]["ackPacketsLost"] > 0
    assert report["transport"]["maxPending"] > 1 and report["transport"]["pending"] == 0
    delivered = [json.loads(line) for line in (output / "websocket.jsonl").read_text().splitlines()]
    assert [frame["sequence"] for frame in delivered] == list(range(12))
    assert any(frame["link"]["status"] == "disconnected" for frame in delivered)
    assert delivered[-1]["link"]["status"] == "degraded"
    for n, frame in enumerate(delivered):
        assert frame["capturedAt"] == rows[n]["capturedAt"]
        assert frame["roverPosition"]["xM"] == n
        assert frame["hazards"][0]["id"] == "rock-1"
        assert frame["hazards"][0]["position"]["xM"] == pytest.approx(n + 1, abs=.001)
        assert frame["hazards"][0]["position"]["yM"] == 0
        assert frame["hazards"][0]["position"]["zM"] == 0


def test_validation_refuses_implicit_synthetic_source(tmp_path):
    from crater_m2.validation import capture_pipeline
    with pytest.raises(ValueError, match="explicit"):
        asyncio.run(capture_pipeline(["--duration", "1"], tmp_path / "validation"))


def test_raw_m1_replay_accepts_explicit_known_ground_height(tmp_path):
    from crater_m2.__main__ import arguments, execute
    source = tmp_path / "observations.jsonl"
    source.write_text(json.dumps(calibrated_rows(1)[0]) + "\n", encoding="utf-8")
    args = arguments(["--input", str(source), "--input-ground-z", "1", "--benchmark",
                      "--duration", "1", "--loss", "0", "--no-blackout",
                      "--report", str(tmp_path / "report.json"),
                      "--received-jsonl", str(tmp_path / "received.jsonl")])
    asyncio.run(execute(args))
    frame = json.loads(args.received_jsonl.read_text())
    assert frame["hazards"][0]["position"] == dict(frameId="LOCAL_ENU_V1", xM=.5, yM=0, zM=1)


def test_slow_websocket_connection_does_not_miss_early_deliveries(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from crater_m2 import validation
    original = validation.connect
    @asynccontextmanager
    async def delayed(url):
        await asyncio.sleep(.5)
        async with original(url) as client:
            yield client
    monkeypatch.setattr(validation, "connect", delayed)
    source = tmp_path / "observations.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in calibrated_rows(3)), encoding="utf-8")
    result = asyncio.run(validation.capture_pipeline([
        "--input", str(source), "--duration", "1", "--drain", "1", "--fps", "20",
        "--bandwidth", "100000", "--latency", "0", "--jitter", "0", "--loss", "0",
        "--no-blackout"], tmp_path / "validation"))
    assert result["webSocketFrames"] == 3 and result["socketMatchesDecodedFrames"]
