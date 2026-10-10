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

## Duplicate boxes

Same-class, nearly concentric nested boxes can be merged even when IoU is
below .5. Containment, center distance and size-ratio gates preserve tiny
rocks inside large terrain boxes and adjacent rocks. The highest confidence
box survives. Tests verify one ID for duplicate boxes and separation of
distinct objects. Replaying the cached NASA crop run removed no additional
boxes; this clip does not establish a measured precision gain.
[Replay evidence](validation/reliability-duplicates.json).

## Temporal confirmation

Tracks begin tentative and become confirmed after two consecutive processed
frames by default. A gap resets the tentative streak; confirmed tracks can
retain identity for up to three missed processed frames. Only fresh observed
boxes are exported, including after a gap. The JSON tracking metadata records
status, total hits and consecutive hits. Tentative obstacles remain visible
immediately by default; `--confirmed-only` opts into delayed export, with
`--track-min-hits` and `--track-max-missed` configurable.

M2 currently ignores the added metadata, so select confirmed-only at M1 when
that behavior is required downstream. Confirmation is temporal persistence,
not proof that a detection is correct. NASA timelapse gaps are not seconds.
Tests cover isolated flashes, streak resets, retained and expired IDs, fresh
export timestamps, and the actual pinned M2 telemetry path.

## Short gaps and identity retention

Camera motion compensation is supplemented with bounded residual velocity
prediction. Strong appearance similarity can rescue a low-IoU match only
within a local distance and size gate; flat patches and distant lookalikes
provide no identity evidence. Missing tracks remain internal and expire;
reappearance after expiry receives a new ID.

The controlled moving-rock gap test uses one ID with prediction versus two
without it. Tests also reject a different texture and a distant lookalike.
A full 43-frame local GPU run retained the baseline 116 observations and
71 allocated IDs, at about .61 seconds/image; the NASA clip therefore shows
no measured ID-retention gain. No tracking accuracy is claimed without
identity labels. Detection scores on both splits are reported separately.
[Final fast-mode evidence](validation/reliability-final-fast.json).
