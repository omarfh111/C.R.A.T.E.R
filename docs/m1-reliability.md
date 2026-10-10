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
