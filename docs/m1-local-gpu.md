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
