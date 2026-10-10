"""IoU precision/recall + ID switches on explicitly scoped annotations."""
from pathlib import Path
import json
import numpy as np
from scipy.optimize import linear_sum_assignment
from .schema import Detection
from .tracking import iou


def evaluate(predictions,annotations,threshold=.5):
    if not 0<threshold<=1: raise ValueError("invalid IoU threshold")
    frames={}
    for line in Path(predictions).read_text(encoding="utf-8").splitlines():
        obj=json.loads(line); index=obj["source"]["frame_index"]
        if index in frames: raise ValueError("duplicate prediction frame")
        frames[index]=obj["detections"]
    truth=json.loads(Path(annotations).read_text(encoding="utf-8"))
    tp=fp=fn=switches=0; last_id={}; overlaps=[]; evaluated=[]
    for frame in truth["frames"]:
        index=frame["frame_index"]
        if index not in frames: raise ValueError(f"annotated frame {index} missing from predictions")
        expected,predicted=frame["detections"],frames[index]
        for d in expected+predicted: Detection(tuple(d["bboxPx"]),d.get("confidence",1.),d["type"])
        if len({d["id"] for d in expected})!=len(expected) or len({d["id"] for d in predicted})!=len(predicted):
            raise ValueError("duplicate object ID within frame")
        scores=np.zeros((len(expected),len(predicted)))
        for i,g in enumerate(expected):
            for j,p in enumerate(predicted):
                if g["type"]==p["type"]: scores[i,j]=iou(g["bboxPx"],p["bboxPx"])
        matches=[]
        if expected and predicted:
            cost=np.ones((len(expected),len(predicted)+len(expected)))
            cost[:,:len(predicted)]=np.where(scores>=threshold,1-scores,2.)
            rows,cols=linear_sum_assignment(cost)
            matches=[(int(i),int(j)) for i,j in zip(rows,cols) if j<len(predicted) and scores[i,j]>=threshold]
        for i,j in matches:
            gt_id=expected[i]["id"]; pred_id=predicted[j]["id"]
            if gt_id in last_id and last_id[gt_id]!=pred_id: switches+=1
            last_id[gt_id]=pred_id; overlaps.append(float(scores[i,j]))
        tp+=len(matches); fp+=len(predicted)-len(matches); fn+=len(expected)-len(matches); evaluated.append(index)
    if not evaluated: raise ValueError("no annotations to evaluate")
    return {"scope":truth.get("scope","unspecified"),"frames_evaluated":evaluated,"iou_threshold":threshold,
        "true_positives":tp,"false_positives":fp,"false_negatives":fn,
        "precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn) if tp+fn else None,
        "matched_mean_iou":float(np.mean(overlaps)) if overlaps else None,"id_switches":switches,
        "tracking_note":"ID switches between successive matches of an annotated ID, including gaps; not IDF1/MOTA."}
