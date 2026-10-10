# Same-model reliability improvements

All experiments retain the pinned Grounding DINO Tiny ONNX weights. The
original three NASA annotation frames are the tuning split. Four additional
frames (5/15/25/35) contain nine provisional manually drawn rock boxes and
are reserved for validation. They were drawn before checking predictions.
These assistant annotations need human review, and both splits come from the
same short timelapse. This is development evidence, not a mission benchmark.
The validation split has no labeled identities and must not report ID accuracy.

The untouched .25-threshold baseline is saved in
[baseline evidence](validation/reliability-baseline.json). Each change is
implemented, tested, measured, committed and pushed separately. Default changes
will be based on tuning evidence; reserved-frame results are reported honestly.

## Threshold selection

`tune-threshold` requires annotations explicitly marked `split: tuning`, reads
the model score floor from the run metrics, and refuses candidate thresholds
below the recorded scores. It maximizes F2 subject to precision >=.9 and never
uses validation labels for selection. The .10/.15/.20 thresholds increased
false positives without recovering the two missed tuning rocks. The measured
selection remains .25; the default is intentionally retained.
[Threshold evidence](validation/reliability-thresholds.json).

```powershell
.\.venv\Scripts\python -m crater_m1 tune-threshold outputs/reliability-raw-scores/observations.jsonl examples/nasa-pilot-annotations.json --output outputs/reliability-thresholds.json
```
