"""Launcher unit tests use an explicit stub, never evidence of ONNX inference."""
import asyncio
import json

import pytest

from crater_m1.simulation import generate
from crater_m2.__main__ import arguments, execute


def options(tmp_path, *extra):
    generate(tmp_path / "scene", count=3)
    return arguments([
        "--perception-video", str(tmp_path / "scene/scene.mp4"),
        "--calibration", str(tmp_path / "scene/calibration.json"),
        "--perception-output", str(tmp_path / "m1"), "--no-preview", "--port", "0",
        "--duration", "3", "--drain", "3", "--fps", "20", "--bandwidth", "10000",
        "--latency", "0", "--jitter", "0", "--loss", "0", "--no-blackout",
        "--report", str(tmp_path / "report.json"),
        "--received-jsonl", str(tmp_path / "received.jsonl"), *extra,
    ])


def test_onnx_dispatch_produces_callback_metrics_without_fallback(tmp_path, monkeypatch):
    from crater_m1.schema import Detection
    constructor = []
    class StubOnnx:
        def __init__(self, **settings): constructor.append(settings)
        def synchronize(self): pass
        def detect(self, image): return [Detection((300, 200, 340, 240), .8)]
        def resources(self): return {"device": "directml", "execution": "unit-test-stub"}
    monkeypatch.setattr("crater_m1.onnx_detector.OnnxGroundingDino", StubOnnx)
    args = options(tmp_path, "--perception-backend", "onnx-grounding-dino", "--device", "directml",
                   "--confirmed-only")
    report = asyncio.run(execute(args))
    assert constructor[0]["device"] == "directml"
    assert report["transport"]["acknowledged"] == 3
    assert report["source"]["perceptionMetrics"]["processed_frames"] == 3
    assert report["source"]["perceptionMetrics"]["backend"] == "onnx-grounding-dino"
    assert report["source"]["perceptionMetrics"]["tracking_settings"]["confirmed_only"] is True
    received = [json.loads(line) for line in args.received_jsonl.read_text().splitlines()]
    assert [len(frame["hazards"]) for frame in received] == [0, 1, 1]
    assert report["source"]["maxSampledBufferedObservations"] <= args.perception_buffer


def test_onnx_initialization_failure_never_runs_synthetic_detector(tmp_path, monkeypatch):
    def failed(**kwargs): raise RuntimeError("prepared ONNX weights missing")
    def forbidden(*args, **kwargs): raise AssertionError("synthetic fallback forbidden")
    monkeypatch.setattr("crater_m1.onnx_detector.OnnxGroundingDino", failed)
    monkeypatch.setattr("crater_m1.detectors.SyntheticContrastDetector", forbidden)
    args = options(tmp_path, "--perception-backend", "onnx-grounding-dino", "--device", "directml")
    with pytest.raises(ValueError, match="prepared ONNX weights missing"):
        asyncio.run(execute(args))
    report = json.loads(args.report.read_text())
    assert not report["completed"] and report["transport"]["generated"] == 0


@pytest.mark.parametrize("backend,device", [("onnx-grounding-dino", "cuda"), ("grounding-dino", "directml")])
def test_incompatible_device_rejected_before_inference(tmp_path, backend, device):
    with pytest.raises(SystemExit):
        options(tmp_path, "--perception-backend", backend, "--device", device)


def test_cloud_backend_cannot_be_selected(tmp_path):
    with pytest.raises(SystemExit):
        options(tmp_path, "--perception-backend", "hf-hosted")


def test_calibrated_ground_plane_is_forwarded_to_m2(tmp_path, monkeypatch):
    from crater_m1.schema import Detection
    class StubOnnx:
        def __init__(self, **kwargs): pass
        def synchronize(self): pass
        def detect(self, image): return [Detection((300, 200, 340, 240), .8)]
        def resources(self): return {"device": "directml", "execution": "unit-test-stub"}
    monkeypatch.setattr("crater_m1.onnx_detector.OnnxGroundingDino", StubOnnx)
    args = options(tmp_path, "--device", "directml")
    poses = json.loads(args.calibration.read_text())
    poses["ground_z_m"] = 1
    args.calibration.write_text(json.dumps(poses))
    report = asyncio.run(execute(args))
    assert report["transport"]["delivered"] == 3
    frames = [json.loads(line) for line in args.received_jsonl.read_text().splitlines()]
    assert all(frame["hazards"][0]["position"]["zM"] == 1 for frame in frames)
