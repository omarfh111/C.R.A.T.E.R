# Windows end-to-end integration

This guide is for `feat/end-to-end-integration`, based on M2 `0f1a53336a0123885494bad33082219f7441a013` with pinned M3 `46bb888282accfdd1e92517d76e442cb986d1ad2` and M1 `94bcf577e0aa5e8f9310d3fadc62757b26ce657b`. It uses local Grounding DINO Tiny ONNX through DirectML, M2 calibrated projection and binary radio, and the M3 LIVE dashboard. Later M2 branch changes are deliberately excluded.

## Prerequisites and local assets

Use Windows 11, a working DirectML GPU driver, Python 3.11 or newer, Node.js 24, and PowerShell. The validated machine has an NVIDIA GeForce RTX 5070 Laptop GPU. The validated Python interpreter is `D:\space_esb_m1\.venv\Scripts\python.exe`; it already contains `onnxruntime-directml==1.24.4`, the model dependencies and the prepared graph. Reuse it for the hardware run. The metadata in `pyproject.toml` declares pytest 8, while this proven interpreter has pytest 9; both the full local suite and a separate hosted pytest 8 CI run passed. Do not replace the working DirectML environment just to change pytest.

The exact local video is `D:\space_esb_m1\outputs\m1-final-scene\scene.mp4`. Its SHA-256 must be `74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9`. The matching calibration and annotations are in that scene directory. The exact 79,774-byte MP4 is also distributed in `examples/m1-onnx-calibrated/scene.mp4` on this integration branch; no GitHub Release was created. Regeneration with `python -m crater_m1 simulate --frames 30 --output <new-directory>` produces a calibrated scene, but encoding may change the video hash; never pair old annotations with a new video.

The model cache is `D:\space_esb_m1\.cache\huggingface`. The model is `onnx-community/grounding-dino-tiny-ONNX` at revision `ff690b0a8050566c290287545bd059350f3e9096`. M1 prepares an FP32 graph from `onnx/model_fp16.onnx`. The prepared graph is about 719 MB and is excluded from Git. The recorded provider list is DirectML then CPU; some operators can run on CPU. A machine without this cache must prepare the same revision using the existing M1 ONNX preparation workflow and normal certificate-verified HTTPS. Windows system CA trust must be repaired if HTTPS fails; never disable TLS verification. Hosted CI and JSONL replay need no model download.

Install frontend packages once:

```powershell
Set-Location D:\space_esb_integration
npm ci
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$env:CRATER_M2_SOURCE = (Get-Location).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
(Get-FileHash 'D:\space_esb_m1\outputs\m1-final-scene\scene.mp4' -Algorithm SHA256).Hash
```

For a new **model-free** Python test environment, use a separate venv; ONNX hardware runs still require the prepared model environment. Do not install over the frozen M1 interpreter:

```powershell
Set-Location D:\space_esb_integration
py -3.12 -m venv .venv-integration-tests
.\.venv-integration-tests\Scripts\python.exe -m pip install -e '.[test]'
```

For a new hardware setup, install the pinned `.[onnx-local]` dependency set in its own venv, then use M1's `download-onnx-model` command with verified HTTPS. The validated Windows CA workaround injects `truststore` into Python's standard SSL stack; see [M1's exact preparation commands](m1-final-validation.md). Do not run model preparation when reusing the already validated cache. Keep each new run's output directory distinct: the validation launcher refuses to overwrite existing evidence.

## Verified evidence and replay

`examples/m1-onnx-calibrated/` contains 30 real ONNX observation frames, camera intrinsics, per-frame camera/rover poses, annotations and a SHA-256 manifest. It includes the exact small source MP4 but no model weights. The exporter normally excludes videos; this distribution supplement is explicitly hash-listed in the manifest. The exporter checks source consistency, hashes, frame coverage and M2 projection; its metadata alone does not independently attest GPU execution. Check every bundled file against `manifest.json` before replay. The [bundle README](../examples/m1-onnx-calibrated/README.md) gives exact Windows commands to prepare the pinned model with certificate-verified HTTPS, rerun ONNX on the distributed MP4, and distinguish fresh inference from historical transport replay:

```powershell
$m = Get-Content examples\m1-onnx-calibrated\manifest.json -Raw | ConvertFrom-Json
foreach ($entry in $m.files.PSObject.Properties) {
  $file = Join-Path examples\m1-onnx-calibrated $entry.Name
  if ((Get-Item $file).Length -ne $entry.Value.bytes) { throw "Size mismatch: $file" }
  if ((Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) {
    throw "SHA-256 mismatch: $file"
  }
}
```

The scene coordinates use `LOCAL_ENU_V1`: x East, y North, z Up, with a known ground plane. Missing or invalid calibration is rejected rather than inferred.

Run the actual integrated M2 WebSocket bridge and M3 parser, using the recorded ONNX observations. This is **historical replay**, not new inference. Capture timestamps remain unchanged and may show STALE in the dashboard.

```powershell
Set-Location D:\space_esb_integration
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
& $py -m crater_m2.validation --output outputs\replay-new --m3-contract src\telemetry\contract.ts -- --input examples\m1-onnx-calibrated\observations.jsonl --input-ground-z 0 --duration 10 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:2 --queue 128 --attempts 20 --seed 7
```

The validator sets offline variables, receives real WebSocket frames, compares them to decoded binary deliveries, and runs the integrated M3 Zod parser. Its `validation.json` and `m2-report.json` are ignored local outputs. `--fps 10` schedules replay observations; it is not measured ONNX throughput. The blackout interval is relative to station mission start.

## Continuous ONNX and LIVE dashboard

Create an ignored `.env.local` in the integration checkout:

```dotenv
VITE_TELEMETRY_MODE=LIVE
VITE_TELEMETRY_WS_URL=ws://127.0.0.1:8765/telemetry
```

Start the frontend in PowerShell terminal A:

```powershell
Set-Location D:\space_esb_integration
npm run dev
```

Open `http://127.0.0.1:5173` in a **fresh browser telemetry session**. Let the cinematic introduction finish. In PowerShell terminal B, set the offline variables above and run:

```powershell
Set-Location D:\space_esb_integration
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$env:CRATER_M2_SOURCE = (Get-Location).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& $py -m crater_m2 --perception-video 'D:\space_esb_m1\outputs\m1-final-scene\scene.mp4' --calibration 'D:\space_esb_m1\outputs\m1-final-scene\calibration.json' --perception-backend onnx-grounding-dino --device directml --cache-dir 'D:\space_esb_m1\.cache\huggingface' --perception-output outputs\demo-perception-new --perception-buffer 4 --no-preview --duration 45 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --no-blackout --queue 128 --attempts 20 --seed 7 --report outputs\demo-m2-new.json --received-jsonl outputs\demo-frames-new.jsonl
```

The M2 station serves `ws://127.0.0.1:8765/telemetry`. Start the browser first so its accepted sequence begins at 0. This single-run command validates live inference without a blackout. For a reliable radio-blackout presentation, follow the measured two-phase sequence in the [seven-minute demo runbook](seven-minute-demo.md): first populate Mission Control, then start a second live run at sequence 30 with a 5:40 second blackout. `--duration` includes model startup; inspect actual reports and capture/arrival times before claiming overlap.

M1 produces detections from video pixels. M2 uses the matching calibrated camera rays and ground plane to produce metric hazards, then sends CRC-protected binary DATA/ACK packets with bounded queue/retries and exposes decoded JSON over WebSocket. The dashboard retains the last accepted frame during radio delay; WebSocket transport state is separate from rover link state. Replayed historical timestamps stay historical. The configured 4,096 bytes/s is a radio simulation setting, not a measured GPU or Internet link rate.

On this Windows DirectML path, native runtime teardown can hang after the producer, bridge and report cleanup. The integrated launcher flushes output before the Windows process termination API. It exits 0 only after the perception producer finishes, all offered observations are consumed and the radio mission completes; an interrupted callback is reported incomplete and exits 2. CPU, replay and non-Windows paths retain ordinary exit behavior. The bounded regression tests cover cleanup ordering and both exit codes; a complete 30-frame DirectML run exited 0.

## Checks, recovery and limitations

```powershell
Set-Location D:\space_esb_integration
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$env:CRATER_M2_SOURCE = (Get-Location).Path
& $py -m pytest -q
& $py -m pytest -q tests\m1
& $py -m pytest -q tests\test_bridge.py tests\test_codec.py tests\test_radio.py tests\test_source.py tests\test_pipeline_validation.py tests\test_end_to_end.py tests\test_directml_shutdown.py
npm test
npm run build
git diff --check
```

If no rocks appear, confirm video hash, calibration, ONNX backend, DirectML provider, threshold and unique output directory; inspect `outputs\demo-perception-new\metrics.json` and M2 report before making changes. If the dashboard says TRANSPORT DOWN, confirm the M2 station is still running and the LIVE URL is correct. If it remains at an older sequence, use a fresh browser session or a strictly increasing `--start-sequence`. If all frames are stale, check whether you are replaying historical observations; never alter capture timestamps. If radio delivery is incomplete, check queue/attempt limits, blackout interval, drain and loss counters. With `--loss .25`, 30/30 delivery was observed for the specified seed and resources, not guaranteed for every configuration.

The synthetic scene demonstrates a calibrated pipeline under known camera/rock geometry. It does not establish lunar accuracy. The three uncalibrated NASA clips remain perception-only evidence; no geographic or metric coordinates are invented for them. M1 detector confidence is not a calibrated probability, the ground-plane projection assumes known planar terrain, and DirectML uses CPU fallback where needed. See [validation evidence](integration-validation.md), [demo runbook](seven-minute-demo.md), [M1 contract](m1-contract.md), [M2 binary protocol](m2-binary-protocol.md), and [M3 telemetry contract](telemetry-contract.md).
