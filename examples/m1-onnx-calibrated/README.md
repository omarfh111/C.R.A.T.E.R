# Calibrated ONNX evidence bundle

This bundle was exported by pinned M2 `crater_m2.handoff` from the frozen M1
run at commit `94bcf577e0aa5e8f9310d3fadc62757b26ce657b`. The integration
baseline is M2 `0f1a53336a0123885494bad33082219f7441a013` and M3
`46bb888282accfdd1e92517d76e442cb986d1ad2`.

`observations.jsonl` contains **actual local Grounding DINO Tiny ONNX
predictions**, not simulator boxes or the synthetic-contrast backend. The
manifest records the reported DirectML provider, model revision, video hash,
calibration and SHA-256 of each exported data file. The exporter checked
source consistency and projected every detection with M2 without rejection;
it did not rerun ONNX or independently attest GPU execution.

The exact source MP4 is retained locally at
`D:\space_esb_m1\outputs\m1-final-scene\scene.mp4` and is **not
distributed** in Git. Its SHA-256 is
`74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9`.
The scene can be regenerated using `python -m crater_m1 simulate --frames 30
--output <fresh-directory>`, but video encoding may change its SHA. Without
the exact MP4, the bundle supports observation replay and hash verification,
not an independent rerun of the original detector input.

`accuracy-*.json` and `m2-spatial-validation.json` describe the controlled
synthetic scene. `m2-radio-report.json` is an earlier **loss-free** M2
benchmark from M1 validation; it is not evidence of lossy delivery. Current
integration replay results belong in ignored local validation outputs and the
integration report. No result here establishes real lunar detection accuracy
or calibrated positions for the uncalibrated NASA videos.

To verify the committed files and replay them from the integration worktree:

```powershell
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
& $py -m crater_m2.validation --output outputs\m1-replay-fresh --m3-contract src\telemetry\contract.ts -- --input examples\m1-onnx-calibrated\observations.jsonl --input-ground-z 0 --duration 10 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:2 --queue 128 --attempts 20 --seed 7
```

Choose a new output directory for each run. The validator checks the actual
WebSocket stream against the integrated M3 Zod contract.
