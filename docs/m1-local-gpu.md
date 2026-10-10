# Local GPU inference on this PC

The inspected PC has an NVIDIA GeForce RTX 3050 Laptop GPU with 6 GB VRAM.
The NVIDIA driver supports CUDA, but the installed PyTorch 2.9.1+cpu build
cannot execute CUDA kernels. `torch.cuda.is_available()` returning false here
does not mean the physical GPU is missing. The earlier HF Space quota concerned
GPU time on the remote server, independently of this PC.

The recommended tested local route is `onnx-grounding-dino` with DirectML on
Windows. DirectML uses the RTX through DirectX 12; this is GPU computation
without a CUDA PyTorch installation. It avoids remote quotas and external
perception APIs. DXGI enumeration selects the dedicated NVIDIA adapter instead
of assuming adapter 0 is always the fastest. Explicit CPU is also supported.

## Setup and execution

```powershell
.\.venv\Scripts\python -m pip install -r requirements-m1-onnx.txt
.\.venv\Scripts\python -m crater_m1 hardware-check
.\.venv\Scripts\python -m crater_m1 download-onnx-model
.\.venv\Scripts\python -m crater_m1 run ..\vid3.mp4 --backend onnx-grounding-dino --device directml --view left --output outputs/nasa-local-gpu
.\.venv\Scripts\python -m crater_m1 evaluate outputs/nasa-local-gpu/observations.jsonl examples/nasa-pilot-annotations.json --output outputs/nasa-local-gpu/accuracy.json
```

The dependencies and weights are already prepared on this PC. Use a new output
directory for another run. `--device auto` selects DirectML when available,
otherwise CPU; `--device cpu` explicitly benchmarks CPU. This ONNX backend
does not accept `--device cuda`; the existing PyTorch backend can use CUDA
only after installing a CUDA PyTorch build and its separate model weights.
No HF_TOKEN is needed for local inference or the public weights download.

## Model and compatibility

Model: `onnx-community/grounding-dino-tiny-ONNX`, pinned revision
`ff690b0a8050566c290287545bd059350f3e9096`.
The downloaded FP16 graph is 360,393,267 bytes. Preparation verifies SHA256
`04c18d2db35569f11c47732f2e05ed3a71559a8903823fc581e90b0e3168c9ff`.
DirectML 1.24.4 rejected this FP16 graph during initialization. Preparation
promotes the already downloaded tensor values and casts to FP32 in a separate
cached graph, with ONNX structural validation. This does not recover precision
lost in the upstream FP16 conversion. It requires extra disk space for the
roughly 719 MB prepared graph, but no additional weights download.

The export requires an exact 800x800 input; the pinned image processor resizes
to that square. Boxes are mapped back to original image coordinates. Supplying
another `--image-size` is rejected. Basic graph optimization avoids an observed
FP16 graph fusion failure. DirectML uses sequential execution and disables
memory-pattern optimization as required by ORT. Unsupported and shape
operators can execute on CPU; provider profiling verifies GPU node execution.
ORT telemetry is disabled. The cached inference test blocks Python socket
connections during both model loading and inference.

Prompt: `rock. stone. boulder.`; threshold .25; text threshold .2. The large-box
filter defaults to .5 of image area and counts rejections. It is a heuristic
that can exclude a very large nearby rock; `--max-rock-area 1` disables it.
Detector scores are not calibrated probabilities. This rock detector is not
validated for craters or slopes. Tracking uses the existing local tracker;
NASA's timelapse image gaps can still disrupt identities. Unknown camera poses
remain null and no metric 3D position is invented.

Sources:
- https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html
- https://huggingface.co/onnx-community/grounding-dino-tiny-ONNX

## Measured validation on this PC

The complete 43-frame left NASA view ran successfully in 26.40 seconds
(excluding model/session loading), with 583.6 ms mean processing latency,
599.7 ms p95 and 1.63 frames/s including preview export. All 43 JSONL entries
and 43 preview frames were verified. The process RAM sample peaked at about
1,447 MB; this does not measure peak GPU VRAM. Outputs:
`outputs/nasa-local-gpu-full/`.

On exactly the same three frames (0/10/20), without preview, CPU mean
processing latency was 9,739.9 ms versus 691.9 ms with DirectML, approximately
14.1 times faster in this sample. Both use the same prepared model, 800x800
input, thresholds and four CPU threads. This is a small comparison, not a
guaranteed speedup for other scenes or hardware. CPU/GPU process RAM peaks
were respectively about 3,997/1,398 MB.

A one-frame ORT profile recorded 1,622 DirectML node events and 39 CPU node
events, confirming actual GPU execution. Counts are not utilization or time
percentages. The real cached model load/inference test passed with Python
socket connections blocked. Local tests passed 61, with only the optional
original PyTorch-weight test skipped. [Saved evidence](validation/local-gpu.json).

The three annotated pilot frames yielded 6 true positives, 0 false positives
and 2 missed rocks at IoU .5 (precision 100%, recall 75% within the specified
>=30x20-pixel scope). This tiny manually labeled sample does not establish
full-video accuracy. The complete run produced 116 observations and 71 tracker
IDs, showing fragmentation under NASA timelapse motion; reliable long-term
identity tracking is not established by this run.
