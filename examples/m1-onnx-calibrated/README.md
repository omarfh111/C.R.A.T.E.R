# Calibrated ONNX evidence bundle

This bundle was exported by pinned M2 `crater_m2.handoff` from the frozen M1 run at commit `94bcf577e0aa5e8f9310d3fadc62757b26ce657b`. The integration baseline is M2 `0f1a53336a0123885494bad33082219f7441a013` and M3 `46bb888282accfdd1e92517d76e442cb986d1ad2`.

`observations.jsonl` contains **actual local Grounding DINO Tiny ONNX predictions**, not simulator boxes or the synthetic-contrast backend. The manifest records M1's reported DirectML provider, pinned model revision, source-video hash, calibration and SHA-256 of every data file. The exporter checked source consistency, all 30 ordered frames and M2 projection without rejected detections. Its metadata does not independently attest GPU execution; the separate local hardware validation does.

The integration branch adds the **exact 79,774-byte source MP4** at [scene.mp4](scene.mp4) as a small distribution supplement to the exporter output. The exporter itself still excludes videos by default. This file was copied byte for byte from `D:\space_esb_m1\outputs\m1-final-scene\scene.mp4`, without re-encoding. Its SHA-256 is `74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9`. It is available from the branch's [raw file](https://raw.githubusercontent.com/omarfh111/C.R.A.T.E.R/feat/end-to-end-integration/examples/m1-onnx-calibrated/scene.mp4); no public GitHub Release was created. The ONNX weights, prepared FP32 graph, virtual environments and generated runs remain outside Git.

The scene is simplified synthetic footage with known camera geometry. Regenerating it with `python -m crater_m1 simulate --frames 30 --output <fresh-directory>` may produce different MP4 bytes, so **never pair regenerated video with these original annotations** unless its SHA-256 matches. These observations and the exact MP4 permit a fresh detector run, but reproducing the original detector output also depends on the pinned model, preprocessing, runtime/provider behavior and settings; identical predictions across hardware are not guaranteed. Transport replay requires no model or GPU and exercises M2/M3 using the previously recorded genuine predictions. These are different reproducibility claims.

`accuracy-*.json` and `m2-spatial-validation.json` describe only this controlled scene. `m2-radio-report.json` is an earlier **loss-free** benchmark, not evidence of lossy delivery. Current integration radio and browser results live in ignored local validation outputs and [integration validation](../../docs/integration-validation.md). No result establishes real lunar detection or mapping accuracy. The uncalibrated NASA videos remain perception-only evidence.

## Verify the distributed source and bundle

From a checkout of `feat/end-to-end-integration` in PowerShell:

```powershell
Set-Location D:\space_esb_integration
$bundle = 'examples\m1-onnx-calibrated'
$m = Get-Content "$bundle\manifest.json" -Raw | ConvertFrom-Json
foreach ($entry in $m.files.PSObject.Properties) {
  $path = Join-Path $bundle $entry.Name
  if ((Get-Item $path).Length -ne $entry.Value.bytes) { throw "Size mismatch: $path" }
  if ((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) { throw "SHA-256 mismatch: $path" }
}
if ((Get-FileHash "$bundle\scene.mp4" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $m.video.sha256) { throw 'Source video mismatch' }
```

The raw file linked above can be downloaded separately with normal HTTPS; verify its SHA-256 before pairing it with the annotations. Never disable TLS certificate verification or use insecure download flags.

## Prepare the exact local model and run fresh inference

On a new Windows machine with a supported DirectML GPU, Python 3.12 and Node.js 24, use a **separate** venv. The validated RTX 5070 host can reuse `D:\space_esb_m1\.venv` and `D:\space_esb_m1\.cache\huggingface` instead. The pinned source is `onnx-community/grounding-dino-tiny-ONNX` revision `ff690b0a8050566c290287545bd059350f3e9096`, file `onnx/model_fp16.onnx` with expected source SHA-256 `04c18d2db35569f11c47732f2e05ed3a71559a8903823fc581e90b0e3168c9ff`. M1 prepares an approximately 719 MB FP32 graph under `.cache\huggingface\prepared-onnx\<revision>\model_fp32.onnx` for DirectML.

```powershell
Set-Location D:\space_esb_integration
py -3.12 -m venv .venv
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
& $py -m pip install -e '.[test,onnx-local]' truststore
& $py -m crater_m1 hardware-check
# This uses the Windows system CA store while keeping HTTPS verification enabled.
& $py -c 'import truststore,sys; truststore.inject_into_ssl(); sys.argv=["crater_m1","download-onnx-model"]; from crater_m1.cli import main; main()'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
& $py -m crater_m1 run examples\m1-onnx-calibrated\scene.mp4 --backend onnx-grounding-dino --device directml --cache-dir .cache\huggingface --calibration examples\m1-onnx-calibrated\calibration.json --threshold .25 --text-threshold .2 --track-min-hits 2 --track-max-missed 3 --no-preview --output "outputs\reproduced-onnx-$tag"
```

The download command verifies the pinned source graph hash before FP32 preparation. After the one-time download, the run above uses the local cache only. Inspect its `metrics.json` for model revision, backend, provider list and processing FPS; compare its output with the original observations and annotations. Do not label newly generated predictions as the historical run or assume identical performance on another GPU. If Windows HTTPS fails, repair system CA trust; never bypass TLS verification.

## Replay recorded predictions through M2 and M3

This path uses the committed, historical ONNX observations and needs **no model weights or GPU**. Choose a fresh output directory for every run:

```powershell
$env:CRATER_M2_SOURCE = (Get-Location).Path
& $py -m crater_m2.validation --output "outputs\m1-replay-$tag" --m3-contract src\telemetry\contract.ts -- --input examples\m1-onnx-calibrated\observations.jsonl --input-ground-z 0 --duration 10 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:2 --queue 128 --attempts 20 --seed 7
```

The validator checks the actual decoded WebSocket frames against the integrated M3 Zod contract. Original capture timestamps remain historical and appear aged/stale in Mission Control; radio loss and blackout are simulated. See the [seven-minute demo](../../docs/seven-minute-demo.md) for the live presentation and explicit replay fallback.
