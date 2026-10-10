import json
from pathlib import Path
import pytest
from crater_m1.evaluation import evaluate


def test_reserved_annotations_have_disjoint_frames_valid_size_and_shared_source():
    root=Path(__file__).resolve().parents[2]
    tuning=json.loads((root/"examples/nasa-pilot-annotations.json").read_text())
    validation=json.loads((root/"examples/nasa-reliability-validation.json").read_text())
    assert tuning["split"]=="tuning" and validation["split"]=="validation"
    assert not {f["frame_index"] for f in tuning["frames"]}&{f["frame_index"] for f in validation["frames"]}
    assert tuning["source_sha256"]==validation["source_sha256"]
    for f in validation["frames"]:
        for d in f["detections"]:
            x1,y1,x2,y2=d["bboxPx"]
            assert 0<x1<x2<1280 and 0<y1<y2<960 and x2-x1>=30 and y2-y1>=20


def test_detection_only_labels_do_not_claim_tracking_accuracy(tmp_path):
    gt=tmp_path/"gt.json";pred=tmp_path/"pred.jsonl"
    gt.write_text(json.dumps({"identity_labels":False,"frames":[{"frame_index":0,"detections":[]}]}))
    pred.write_text(json.dumps({"source":{"frame_index":0},"detections":[]}))
    assert evaluate(pred,gt)["id_switches"] is None
