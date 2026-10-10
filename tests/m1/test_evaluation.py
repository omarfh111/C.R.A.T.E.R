import json
import pytest
from crater_m1.evaluation import evaluate


def test_evaluator_counts_false_detections_and_identity_switch(tmp_path):
    gt={"frames":[{"frame_index":i,"detections":[{"id":"rock-a","type":"rock","bbox_px":[10,10,30,30]}]} for i in range(3)]}
    pred=[]
    for i in range(3):
        ds=[{"id":f"track-{i}","type":"rock","bbox_px":[10,10,30,30],"confidence":.8}] if i<2 else []
        ds.append({"id":"extra","type":"rock","bbox_px":[80,80,90,90],"confidence":.8})
        pred.append({"source":{"frame_index":i},"detections":ds})
    a=tmp_path/"gt.json"; p=tmp_path/"pred.jsonl"
    a.write_text(json.dumps(gt)); p.write_text("\n".join(json.dumps(f) for f in pred))
    r=evaluate(p,a)
    assert (r["true_positives"],r["false_positives"],r["false_negatives"],r["id_switches"])==(2,3,1,1)
    p.write_text(json.dumps(pred[0]))
    with pytest.raises(ValueError,match="missing"): evaluate(p,a)
