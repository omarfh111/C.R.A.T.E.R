# M1 calibrated ONNX validation and M2 handoff

Validation on 2026-10-10 used `feat/ai-perception`, Python 3.12.14, an RTX 5070
Laptop GPU (driver 591.59), ONNX Runtime DirectML 1.24.4, and the pinned
`onnx-community/grounding-dino-tiny-ONNX` revision
`ff690b0a8050566c290287545bd059350f3e9096`. M2 was inspected in an
isolated checkout at `8b1b95e7051fba592c22b5299cf545915c4b083b`.
Inference was local; no cloud backend, CUDA PyTorch model, substituted boxes,
or model fine-tuning was used. The downloaded FP16 graph was checksum-verified
and promoted to FP32 by the existing preparation command. A one-frame runtime
profile recorded 1,622 DirectML node executions and 39 CPU node executions.

## Calibrated scene result

`crater_m1.simulation.generate` rendered 30 frames with three known ground
points, camera intrinsics, a per-frame camera center and rotation, rover pose,
and independent rock annotations. The ONNX pipeline processed every frame with
`--device directml --calibration`, producing
`outputs/m1-final-onnx/observations.jsonl`. The annotation SHA-256 matched the
rendered MP4. No simulator truth was supplied to the detector or tracker.

At IoU 0.5, the existing evaluator found 90 true positives, 0 false positives,
0 misses, mean matched IoU 0.814, and 0 ID switches over all 30 frames.
Reserved frames 15–29 had 45 true positives, 0 false positives, 0 misses,
mean matched IoU 0.815, and 0 ID switches. Each of the three ground-truth
rocks kept one M1 track ID across the run. Processing throughput was 3.24 FPS
and end-to-end throughput was 3.23 FPS, without preview encoding. Model/session
loading is excluded; first inference is included.

M2's current `observation_to_frame` accepted all 30 lines and projected all
90 **ONNX-detected** contacts into `LOCAL_ENU_V1`, with no rejected hazards.
M2's own virtual radio replay then generated, delivered and acknowledged all
30 canonical frames with 0 rejected detections under an explicitly loss-free
4,096-byte/s link. This tests JSONL ingestion, spatial conversion, encoding,
and transport; it does not prove behavior under real packet loss or a live
WebSocket dashboard.
Matching detections to independent truth by IoU >= 0.5, then measuring ENU
distance from M2's projected positions to the known ground points, gave:

| Frames | Matched | Mean error | Median | P95 | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0–29 | 90 | 0.097 m | 0.082 m | 0.193 m | 0.213 m |
| 15–29 | 45 | 0.094 m | 0.086 m | 0.182 m | 0.203 m |

All measured errors fell within M2's reported uncertainty radius for this
scene. M2 rejected the same observation when its camera calibration was set to
null. The generated JSONL contains timestamps, camera intrinsics and moving
pose, `LOCAL_ENU_V1` rover position, pose uncertainty, model confidence,
contact pixels, and stable IDs. M2 ignores M1's extra source/image metadata.

This is a simple, correlated synthetic scene with exact camera calibration and
a flat ground plane. Reserved frames test unseen timestamps and camera poses
within the same scene; they do not establish performance on new terrain.
The contact pixel is the bottom of a detected box, not a measured 3D point.
The uncertainty result depends on the supplied pose budget and does not prove
a bound under real calibration or terrain error.

## NASA video check

The three supplied videos ran end to end through the same local ONNX model:

| Input | Frames | Processing FPS | Detections | Unique track IDs |
| --- | ---: | ---: | ---: | ---: |
| `videos_test/vid1.mp4` | 1,367 | 3.94 | 3,027 | 95 |
| `videos_test/vid2.mp4` | 53 | 2.99 | 473 | 301 |
| `videos_test/vid3.mp4` (left view) | 43 | 2.67 | 116 | 71 |

`vid2` and `vid3` produced many short or tentative tracks (324/473 and 71/116
observations respectively). Their timelapse viewpoint changes limit persistent
identity claims. The checked-in NASA annotations require source SHA-256
`d7f157de...`, which matches none of the supplied MP4 files; no precision or
recall was calculated from those labels. These videos have no calibration, so
their observations must not be used for metric M2 localization.

## Reproduce on Windows PowerShell

Run from the repository root on `feat/ai-perception`. On this host Python 3.12
is bundled at the path below; another host can use its own Python 3.12.
DirectML uses the NVIDIA GPU while the small CPU PyTorch wheel is needed for
the model processor and output decoding. Keep the weights under the ignored
`.cache/huggingface` directory.

```powershell
& 'C:\Users\moham\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
& $py -m pip install -e '.[test,onnx-local]' truststore
& $py -m crater_m1 hardware-check
```

On this Windows host, `requests`' bundled CA file did not trust the certificate
chain that Windows trusted. The following download uses the Windows CA store
through `truststore` and keeps TLS verification enabled. It downloads only the
pinned ONNX weights and processor files, then checks the graph SHA-256.

```powershell
& $py -c 'import truststore,sys; truststore.inject_into_ssl(); sys.argv=["crater_m1","download-onnx-model"]; from crater_m1.cli import main; main()'
& $py -m crater_m1 simulate --output outputs/m1-final-scene --frames 30
& $py -m crater_m1 run outputs/m1-final-scene/scene.mp4 --backend onnx-grounding-dino --device directml --calibration outputs/m1-final-scene/calibration.json --no-preview --output outputs/m1-final-onnx
& $py -m crater_m1 evaluate outputs/m1-final-onnx/observations.jsonl outputs/m1-final-scene/annotations.json --output outputs/m1-final-onnx/accuracy-all.json
```

To reproduce the reserved-frame score, retain the annotation SHA-256 and keep
only frames 15–29. Use fresh output directory names when repeating the run;
the pipeline refuses to overwrite existing observations.

```powershell
& $py -c 'import json,pathlib; p=pathlib.Path("outputs/m1-final-scene/annotations.json"); d=json.loads(p.read_text()); d["frames"]=[f for f in d["frames"] if f["frame_index"]>=15]; d["scope"]="Reserved synthetic frames 15-29"; pathlib.Path("outputs/m1-final-scene/annotations-heldout.json").write_text(json.dumps(d))'
& $py -m crater_m1 evaluate outputs/m1-final-onnx/observations.jsonl outputs/m1-final-scene/annotations-heldout.json --output outputs/m1-final-onnx/accuracy-heldout.json
```

The spatial check used `scipy.optimize.linear_sum_assignment` to match M1
boxes to truth boxes by IoU, retaining matches at IoU >= 0.5. It passed each
unaltered M1 observation to M2 `observation_to_frame` and measured Euclidean
distance from each matched M2 hazard to the independent rock position. The
per-match data and summary are in the ignored local file
`outputs/m1-final-onnx/m2-spatial-validation.json`. M2 received only M1
observations; ground truth was read afterward for measurement.

To replay the actual ONNX JSONL through M2's input adapter and virtual radio,
run from the M1 checkout after the isolated M2 clone below:

```powershell
$env:PYTHONPATH = (Resolve-Path outputs/m2-latest).Path
& $py -m crater_m2 --benchmark --input outputs/m1-final-onnx/observations.jsonl --fps 10 --duration 3 --drain 30 --queue 128 --bandwidth 4096 --latency .005 --jitter 0 --loss 0 --no-blackout --report outputs/m1-final-onnx/m2-radio-report.json --received-jsonl outputs/m1-final-onnx/m2-received-frames.jsonl
```

For M2 contract tests, use a separate checkout; never merge or modify M2 for
this check. The real ONNX offline test needs frame 10 of the left view saved as
`outputs/inspection/left-10.jpg` (see `tests/m1/test_onnx_detector.py`).

```powershell
git clone --single-branch --branch feat/spatial-telemetry https://github.com/omarfh111/C.R.A.T.E.R outputs/m2-latest
git -C outputs/m2-latest checkout 8b1b95e7051fba592c22b5299cf545915c4b083b
& $py -c 'from pathlib import Path; import cv2; from crater_m1.video import frames; p=Path("outputs/inspection/left-10.jpg"); p.parent.mkdir(parents=True,exist_ok=True); image=next(image for index,_,image,_ in frames("videos_test/vid3.mp4",view="left") if index==10); assert cv2.imwrite(str(p),image)'
$env:CRATER_M2_SOURCE = (Resolve-Path outputs/m2-latest).Path
$env:CRATER_ONNX_SMOKE = '1'
$env:CRATER_REQUIRE_DIRECTML = '1'
& $py -m pytest tests/m1 -q
Push-Location outputs/m2-latest
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& D:\space_esb_m1\.venv\Scripts\python.exe -m pytest tests/test_source.py tests/test_geometry.py tests/test_contract.py -q -p no:cacheprovider
Pop-Location
```

On the validated host, M1 against latest M2 passed **85 tests with one skip**.
The skipped test requires separate PyTorch model weights and was outside this
ONNX-only validation. M2 source, geometry and contract tests passed **40/40**.
The pytest cache provider was disabled for that isolated checkout because its
teardown hung on this host after all tests had printed; tests then exited cleanly.
`pip check` reported no broken dependencies.

## Decision

**GO for controlled M1-to-M2 integration** with this calibrated scene and the
validated JSONL. **NO-GO for claims of real lunar metric accuracy** until real
footage has measured calibration, suitable ground truth, and independent
evaluation. Generated videos, model files, benchmark outputs, and JSONL are
ignored local artifacts and are not committed.
