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


def test_threshold_selection_uses_tuning_only_and_respects_score_floor(tmp_path):
    from crater_m1.tuning import sweep_thresholds
    gt=tmp_path/"gt.json";pred=tmp_path/"pred.jsonl"
    detection={"id":"truth","type":"rock","bboxPx":[10,10,30,30]}
    gt.write_text(json.dumps({"split":"tuning","frames":[{"frame_index":0,"detections":[detection]}]}))
    pred.write_text(json.dumps({"source":{"frame_index":0},"detections":[{**detection,"confidence":.2},{"id":"false","type":"rock","bboxPx":[70,70,90,90],"confidence":.1}]}))
    (tmp_path/"metrics.json").write_text(json.dumps({"model_resources":{"threshold":.1}}))
    report=sweep_thresholds(pred,gt,[.1,.15,.25],min_precision=.9)
    assert report["recommended_threshold"]==.15
    assert report["results"][1]["recall"]==1 and report["results"][0]["false_positives"]==1
    with pytest.raises(ValueError,match="score floor"): sweep_thresholds(pred,gt,[.05])
    data=json.loads(gt.read_text());data["split"]="validation";gt.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="reserved"): sweep_thresholds(pred,gt,[.15])
