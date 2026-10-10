"""Exporter tests use simulated pixels and explicitly fabricated model metadata.

They verify handoff checks, never actual ONNX inference or GPU performance.
"""
import json

import pytest

from crater_m1.detectors import SyntheticContrastDetector
from crater_m1.pipeline import run
from crater_m1.simulation import generate


def prepared(tmp_path):
    scene, predictions = tmp_path / "scene", tmp_path / "run"
    generate(scene, count=2)
    run(scene / "scene.mp4", predictions, SyntheticContrastDetector(),
        calibration=scene / "calibration.json", preview=False)
    metrics_path = predictions / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    # Fabricated metadata is confined to this unit fixture.
    metrics["model_resources"] = dict(execution="local-onnx", device="directml",
        model_id="onnx-community/grounding-dino-tiny-ONNX",
        model_revision="ff690b0a8050566c290287545bd059350f3e9096",
        providers=["DmlExecutionProvider", "CPUExecutionProvider"])
    metrics_path.write_text(json.dumps(metrics))
    return scene, predictions


def test_handoff_preserves_original_files_and_excludes_weights_video(tmp_path):
    from crater_m2.handoff import export_handoff
    scene, predictions = prepared(tmp_path)
    output = tmp_path / "handoff"
    result = export_handoff(scene, predictions, output)
    assert result["frames"] == 2
    assert (output / "observations.jsonl").read_bytes() == (predictions / "observations.jsonl").read_bytes()
    assert set(p.name for p in output.iterdir()) == {
        "observations.jsonl", "calibration.json", "annotations.json", "metrics.json", "manifest.json"}
    assert result["video"]["sha256"] == json.loads((scene / "annotations.json").read_text())["source_sha256"]


@pytest.mark.parametrize("invalid", ["model", "video", "pose", "count"])
def test_inconsistent_handoff_is_rejected_before_writing(tmp_path, invalid):
    from crater_m2.handoff import export_handoff
    scene, predictions = prepared(tmp_path)
    if invalid in ("model", "count"):
        path = predictions / "metrics.json"
        obj = json.loads(path.read_text())
        if invalid == "model": obj["model_resources"]["execution"] = "synthetic"
        else: obj["processed_frames"] = 30
        path.write_text(json.dumps(obj))
    elif invalid == "video":
        with (scene / "scene.mp4").open("ab") as stream: stream.write(b"changed")
    else:
        path = scene / "calibration.json"
        obj = json.loads(path.read_text())
        obj["frames"]["0"]["camera"]["fx"] += 1
        path.write_text(json.dumps(obj))
    output = tmp_path / "handoff"
    with pytest.raises(ValueError): export_handoff(scene, predictions, output)
    assert not output.exists()


def test_handoff_does_not_overwrite_existing_directory(tmp_path):
    from crater_m2.handoff import export_handoff
    output = tmp_path / "handoff"
    output.mkdir()
    with pytest.raises(ValueError, match="exists"):
        export_handoff(tmp_path / "missing", tmp_path / "missing", output)
