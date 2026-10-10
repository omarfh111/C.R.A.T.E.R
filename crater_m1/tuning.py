"""Reproducible threshold selection using only an explicitly marked tuning split."""
import json
import math
from pathlib import Path
import tempfile
from .evaluation import evaluate


def sweep_thresholds(predictions,annotations,candidates=(.1,.15,.2,.25,.3,.35),min_precision=.9):
    predictions=Path(predictions);annotations=Path(annotations)
    truth=json.loads(annotations.read_text())
    if truth.get("split")!="tuning": raise ValueError("threshold selection requires a tuning split; validation labels are reserved")
    if not math.isfinite(min_precision) or not 0<min_precision<=1: raise ValueError("invalid minimum precision")
    settings=json.loads((predictions.parent/"metrics.json").read_text())
    floor=settings["model_resources"]["threshold"]
    if not math.isfinite(floor) or not 0<floor<1: raise ValueError("invalid prediction score floor")
    candidates=sorted(set(candidates))
    if not candidates or any(not math.isfinite(t) or not floor<=t<1 for t in candidates):
        raise ValueError("candidate thresholds must be at least the recorded prediction score floor")
    rows=[json.loads(line) for line in predictions.read_text().splitlines()]
    results=[]
    with tempfile.TemporaryDirectory(prefix="crater-tune-") as folder:
        filtered=Path(folder)/"predictions.jsonl"
        for threshold in candidates:
            filtered.write_text("\n".join(json.dumps({**row,"detections":[d for d in row["detections"] if d["confidence"]>=threshold]}) for row in rows))
            result=evaluate(filtered,annotations)
            tp,fp,fn=(result[k] for k in ("true_positives","false_positives","false_negatives"))
            result.update(threshold=threshold,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                f2=5*tp/(5*tp+fp+4*fn) if 5*tp+fp+4*fn else None)
            results.append(result)
    eligible=[r for r in results if r["precision"] is not None and r["precision"]>=min_precision and r["f2"] is not None]
    best=max(eligible,key=lambda r:(r["f2"],r["precision"],r["threshold"])) if eligible else None
    return {"selected_from":"tuning","min_precision":min_precision,"score_floor":floor,
        "recommended_threshold":best["threshold"] if best else None,"selection_rule":"maximum F2 subject to minimum precision; ties prefer higher precision then higher threshold",
        "results":results,"note":"Same-video provisional labels; selection is not a guarantee of deployment reliability."}
