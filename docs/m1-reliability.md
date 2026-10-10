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

## Overlapping crops

`--tiles 2x2` runs the full image plus four overlapping crops through the same
model. Crop boxes are mapped to original pixels; internal seam-truncated
boxes are discarded and duplicates are merged. Any crop failure rejects the
whole frame. The tuning set improved from 6/8 to 7/8 matched rocks with no
additional scoped false positive. Five inference calls increase processing
latency to about 2.9 seconds/image in the eight-frame check, so crops are opt-in.
[Crop tuning, reserved results and timing](validation/reliability-tiles.json).

## Large close rocks

The default ONNX `--terrain-filter edges` rejects oversized boxes only when
they span almost the entire image width. Localized close rocks survive even
above the .5 area limit. `area` restores the legacy blanket area filter, and
`off` disables this heuristic for ambiguous full-width close objects. This
is a box heuristic, not terrain classification. Unit tests cover large close
rocks and wide ground boxes; the eight-frame NASA comparison was unchanged.
[Terrain evidence](validation/reliability-terrain.json).
