"""Export existing calibrated M1 ONNX evidence; no inference or downloads.

Checks establish file consistency and reported provenance, not independent
proof that inference executed on a GPU. Video and model weights stay external.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from .source import observation_to_frame


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_handoff(scene, run, output):
    scene, run, output = (Path(p).resolve() for p in (scene, run, output))
    if output.exists():
        raise ValueError("handoff output already exists; choose a new directory")
    if output.is_relative_to(scene) or output.is_relative_to(run):
        raise ValueError("handoff output must be separate from source directories")
    files = {"observations.jsonl": run / "observations.jsonl", "metrics.json": run / "metrics.json",
             "calibration.json": scene / "calibration.json", "annotations.json": scene / "annotations.json"}
    # Snapshot small files once so checks and exported bytes refer to the same data.
    contents = {name: path.read_bytes() for name, path in files.items()}
    metrics = json.loads(contents["metrics.json"])
    calibration = json.loads(contents["calibration.json"])
    annotations = json.loads(contents["annotations.json"])
    model = metrics["model_resources"]
    if (model.get("execution") != "local-onnx" or model.get("device") != "directml"
            or model.get("model_id") != "onnx-community/grounding-dino-tiny-ONNX"
            or model.get("model_revision") != "ff690b0a8050566c290287545bd059350f3e9096"
            or "DmlExecutionProvider" not in model.get("providers", [])):
        raise ValueError("metrics must report the pinned local ONNX model with DirectML")
    video_hash = sha256(scene / "scene.mp4")
    if annotations.get("source_sha256") != video_hash or metrics["video"]["sha256"] != video_hash:
        raise ValueError("annotations/metrics do not match the actual source video SHA-256")
    ground_z = calibration.get("ground_z_m", 0)
    if calibration.get("frameId") != "LOCAL_ENU_V1" or type(ground_z) not in (int, float) or not math.isfinite(ground_z):
        raise ValueError("calibration must use LOCAL_ENU_V1 with a finite ground plane")
    rows = [json.loads(line) for line in contents["observations.jsonl"].splitlines() if line.strip()]
    if not rows or len(rows) != metrics["processed_frames"]:
        raise ValueError("observation count differs from processed_frames")
    indices = []
    for sequence, row in enumerate(rows):
        source = row["source"]
        if source["file_sha256"] != video_hash or row["perception"]["execution"] != "local":
            raise ValueError("observations must report local inference on the same source video")
        index = source["frame_index"]
        if type(index) is not int or index < 0:
            raise ValueError("invalid original frame index")
        indices.append(index)
        pose = calibration["frames"][str(index)]
        position = row["roverPosition"]
        if (row["camera"] != pose["camera"]
                or [position[k] for k in ("xM", "yM", "zM")] != pose["roverPositionEnuM"]
                or row["positionUncertaintyRadiusM"] != pose["positionUncertaintyRadiusM"]
                or row.get("groundZM", ground_z) != ground_z):
            raise ValueError("observation camera/pose/ground plane differs from its calibration")
        result = observation_to_frame(dict(row, groundZM=ground_z), sequence,
            dict(status="connected", packetsSent=0, packetsLost=0))
        if result.rejected:
            raise ValueError(f"frame {index} has rejected spatial detections: {result.rejected}")
    if indices != sorted(set(indices)):
        raise ValueError("original frame indices must be unique and chronological")
    if indices != [frame["frame_index"] for frame in annotations["frames"]]:
        raise ValueError("annotations must cover the same ordered frames as predictions")
    # Only known small reports are included; cache, environment and videos are excluded.
    for name in ("accuracy-all.json", "accuracy-heldout.json", "m2-spatial-validation.json", "m2-radio-report.json"):
        path = run / name
        if path.is_file():
            content = path.read_bytes()
            json.loads(content)
            contents[name] = content
    manifest = dict(schemaVersion=1, frames=len(rows), groundZM=ground_z,
        video=dict(file="scene.mp4", sha256=video_hash, distribution="external attachment; excluded from Git bundle"),
        reportedModel=model,
        evidenceNote="Metadata is reported by M1. Export checks do not run ONNX or independently attest GPU execution. Existing reports may concern an older M2; run latest live validation separately.",
        files={name: dict(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
               for name, content in contents.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="m1-handoff-", dir=output.parent) as temporary:
        bundle = Path(temporary) / "bundle"
        bundle.mkdir()
        for name, content in contents.items():
            (bundle / name).write_bytes(content)
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        bundle.rename(output)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = export_handoff(args.scene, args.run, args.output)
        print(f"Exported {result['frames']} calibrated observations to {args.output.resolve()}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Handoff export failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
