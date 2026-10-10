import json
from pathlib import Path
import cv2
from crater_m1.detectors import SyntheticContrastDetector
from crater_m1.pipeline import run
from crater_m1.simulation import generate
from crater_m1.evaluation import evaluate


def test_real_pixels_to_tracks_jsonl_preview_and_metrics(tmp_path):
    source=tmp_path/"scene"; generate(source,count=8)
    output=tmp_path/"run"
    metrics=run(source/"scene.mp4",output,SyntheticContrastDetector(),calibration=source/"calibration.json")
    assert metrics["processed_frames"]==8
    assert metrics["processing_fps"]>0
    frames=[json.loads(line) for line in (output/"observations.jsonl").read_text().splitlines()]
    assert all(len(f["detections"])==3 for f in frames)
    assert len({d["id"] for f in frames for d in f["detections"]})==3
    assert frames[0]["camera"]["width"]==640
    assert "position" not in frames[0]["detections"][0]
    report=evaluate(output/"observations.jsonl",source/"annotations.json")
    assert report["precision"]==report["recall"]==1
    assert report["id_switches"]==0
    cap=cv2.VideoCapture(str(output/"preview.mp4"))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT))==8
    cap.release()


def test_uncalibrated_video_emits_no_metric_pose(tmp_path):
    generate(tmp_path/"scene",count=2)
    run(tmp_path/"scene/scene.mp4",tmp_path/"run",SyntheticContrastDetector(),preview=False)
    frame=json.loads((tmp_path/"run/observations.jsonl").read_text().splitlines()[0])
    assert frame["camera"] is None and frame["rover_position_enu_m"] is None
