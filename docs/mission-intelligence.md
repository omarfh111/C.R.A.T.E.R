# Optional Mission Intelligence

Mission Intelligence adds a read-only inspector to the existing Mission Control dashboard. Its immediate explanations use accepted WebSocket v1 telemetry. An optional local science assistant retrieves curated references and generates clearly unverified context. Neither layer changes rover telemetry, hazards, radio behavior, or mission decisions.

The original two-command, GPU-free Quick Demo remains the default:

```powershell
.\scripts\setup.ps1
.\scripts\start-demo.ps1
```

These commands do not start Ollama, require assistant models, or download new model weights. Historical ONNX replay remains historical; LIVE identifies the dashboard's WebSocket connection, not fresh camera inference.

## Inspect an accepted observation

Open **Mission Intelligence** in the existing dashboard and select a hazard on the tactical map. The inspector explains the selected accepted observation and, where available, the latest rover fix:

- Detection identity, type, capture time, and transmitted local ENU coordinates.
- Detector confidence, explicitly a detector score rather than a calibrated probability.
- The transmitted uncertainty radius, without presenting it as a certified statistical interval.
- Horizontal separation from the same rover's latest fix. The hazard and rover fix may have different timestamps; this is not a new ranging measurement.
- Observation age, receipt age, and stale or unknown clock state. Capture-to-receipt interval can include replay age and clock differences; it is not automatically network latency.
- The frame's reported link status and rover packet counters, separately from frontend accepted frames, sequence gaps, and station connection state.

Missing telemetry or calibration remains missing. The panel does not infer missing calibration, invent sensor values, or run image understanding. The calibrated evaluation scene is synthetic, its ONNX detections came from actual pixels, and the Quick Demo radio interruptions are simulated. WebSocket v1 does not independently certify whether every upstream observation is measured or simulated.

The assistant question path sends a question and passage count only. It does not upload the selected telemetry frame and does not write its answer into telemetry state. Current operational measurements belong to the deterministic inspector, not the science model.

## Enable local AI on Windows

Use the assistant **after live GPU capture has finished**. Keep the dashboard open for observation review or historical replay. Close the assistant launcher with **Ctrl+C before starting another live capture**.

The tested optional runtime uses Windows, an NVIDIA RTX 5070 Laptop GPU, Ollama 0.40.2, and these already installed models:

- `qwen3:4b-instruct-2507-q4_K_M`
- `embeddinggemma:300m`

The launcher requires `nvidia-smi.exe`, at least 4096 MiB of free NVIDIA memory, the existing model-free `.venv`, and an installed `ollama.exe`. It uses existing model files and never installs software or pulls models. PDF extraction is a separate optional `assistant` package extra; it is unnecessary for this curated Markdown corpus. No cloud credentials are used.

In a second PowerShell window in the repository, use the **actual dashboard origin printed by the Quick Demo launcher**, omitting its final slash. This example port is not fixed:

```powershell
Set-Location D:\space_esb_m2_assistant_integration
.\scripts\start-assistant.ps1 -DashboardOrigin 'http://127.0.0.1:50554'
```

The script normally owns a separate Ollama server at `http://127.0.0.1:11435` and an HTTP sidecar at `http://127.0.0.1:8766`. It refuses occupied ports instead of stopping their owners. If necessary, choose two other free ports:

```powershell
.\scripts\start-assistant.ps1 `
  -DashboardOrigin 'http://127.0.0.1:50554' `
  -AssistantPort 8767 -OllamaPort 11436
```

It never manages the shared/default Ollama port 11434. `-OllamaExecutable`, `-PythonPath`, and `-GpuUuid` can select existing installations. The advanced `-UseExistingOllama` switch connects to an explicitly selected, already running isolated server; that runtime's configuration, model lifetime, and eventual unloading remain the operator's responsibility. Prefer the ordinary owned-server mode for reliable cleanup.

Startup checks model metadata, builds a local index from the corpus manifest, preloads Qwen, and exercises retrieval plus generation with a fixed NASA question before exposing the HTTP service. The first CUDA loading/kernel-compilation run took about **110 seconds** in the benchmark, so prepare this optional runtime outside the seven-minute rover demo. Startup CLI calls have a 180-second budget and a 200-second stage watchdog. Subsequent operator HTTP questions have an aggregate **45-second** backend deadline.

When the launcher prints that the service is ready, enter its URL in the panel and select **CONNECT LOCAL AI**, then **ASK REFERENCES**. No source edits or `.env` changes are needed. Sources, excerpts, citation IDs, and limitations appear with the answer. The panel distinguishes loading, unavailable, busy, timeout, invalid response, failed, cancelled, and insufficient evidence. Disconnecting or losing Ollama leaves deterministic explanations and the dashboard usable.

The launcher checks for live M1/M2 capture throughout startup and operation, and `serve --block-live-m1` checks admission on each question. If capture appears, the launcher stops its owned Ollama tree first and then its sidecar. These process checks are a best-effort safeguard, not an atomic hardware lock against another application starting. Operational sequencing remains required: stop AI before live capture. Historical `--input` replay is allowed.

Ctrl+C and startup failures clean up only processes created by this launcher, including their children. Logs, the local evidence index, and the fixed startup answer are written to a unique `outputs/assistant-...` directory. These outputs may contain excerpts and local document paths; keep them local unless deliberately reviewed for publication.

## Runtime strategy and GPU evidence

The isolated child process selects the NVIDIA GPU by UUID and disables AMD/HIP/Vulkan/iGPU discovery. Child-only environment settings include `OLLAMA_LLM_LIBRARY=cuda_v13`, `OLLAMA_IGPU_ENABLE=false`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_MAX_QUEUE=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_NO_CLOUD=1`, and `OLLAMA_NOPRUNE=1`. Existing shells and shared Ollama configuration are not rewritten.

The selected answer budget is **4096 context tokens, up to 240 output tokens, three retrieved passages, and 120 seconds keep-alive**. Keeping models resident avoids loading for every question; they may unload after inactivity. Shorter 2048-token experiments did not improve the measured latency and reduce context headroom. The CLI's conservative defaults remain separate; use the launcher for the selected product settings.

Final measured local model identities on 2026-10-11:

| Model | Quantization / size | Ollama digest |
| --- | --- | --- |
| Qwen3 4B Instruct 2507 | Q4_K_M; 2,497,293,803 stored bytes | `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` |
| EmbeddingGemma 300M | BF16; 621,875,861 stored bytes | `5265a4c1d1e7ef31b67da5be71b21030cf8f3f0ffab7b38614866c4e92a8c4b5` |

The initial default-discovery experiment reported EmbeddingGemma digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1` and different runner metadata, then reported the final identity later. No model pull/create/fine-tuning command was invoked. The manifest metadata changed, but bit-identical old/new weights were not independently established. All final NVIDIA comparisons identify EmbeddingGemma as `5265a4c1...`; its index must not be reused under another identity. A requested GPU flag alone was insufficient: initial AMD/default discovery is not evidence of NVIDIA acceleration. The final isolated run reports NVIDIA CUDA loading and nonzero `/api/ps.size_vram` for both selected models; [CUDA log excerpts and residency](validation/mission-intelligence/gpu-runtime.json) preserve the 25/25 embedding and 37/37 Qwen layer-offload evidence.

At context 4096, Ollama reported 3,178,149,969 bytes (about 3031 MiB) of Qwen GPU residency and 681,417,113 bytes (about 650 MiB) for EmbeddingGemma. Qwen at context 8192 reported about 3694 MiB. These are model residency reports, not device-wide allocation peaks. The coexistence experiment observed **7212 MiB device-wide** use with M1 and both models resident on an approximately 8 GB GPU; that leaves little headroom for other GPU applications.

## Measured latency

[NVIDIA benchmark evidence](validation/mission-intelligence/nvidia-benchmark.json) compares the pinned M2 adapter using an identical prepared question and supplied excerpts. It does **not** include RAG retrieval in each chat measurement. In this archived record, top-level `elapsedS` includes metadata calls and resource-monitor teardown (up to a three-second join), but excludes the separately recorded preload. Report that value as legacy harness elapsed, not pure HTTP answer latency. The current harness records sampler teardown separately as `samplerTeardownS`. `calls[].elapsedS` measures the individual Ollama HTTP call; Ollama duration fields are server-reported nanoseconds.

| Prepared chat case | Context / output / passages | Harness elapsed | `/api/chat` HTTP | Load / prompt / generation | Output tokens/s |
| --- | --- | ---: | ---: | --- | ---: |
| Existing CPU, unload each call | 8192 / 600 / 4 | 35.28 s | 27.72 s | 8.21 / 10.11 / 8.59 s | 14.66 |
| First NVIDIA cold run | 8192 / 600 / 4 | 109.75 s | 105.94 s | 52.45 / 48.30 / 4.73 s | 34.02 |
| Preloaded NVIDIA | 8192 / 600 / 4 | 7.83 s | 3.66 s | 0.15 / 0.46 / 2.53 s | 63.76 |
| Warm NVIDIA | 8192 / 600 / 4 | 6.36 s | 2.62 s | 0.11 / 0.06 / 2.05 s | 79.10 |
| Subsequent NVIDIA cold | 4096 / 240 / 3 | 8.71 s | 5.88 s | 3.05 / 0.38 / 1.91 s | 63.25 |
| Warm NVIDIA | 4096 / 240 / 3 | 5.71 s | 2.18 s | 0.08 / 0.02 / 1.70 s | 75.31 |
| Warm NVIDIA, smaller budget | 2048 / 160 / 3 | 7.94 s | 3.09 s | 0.20 / 0.18 / 1.80 s | 71.01 |

The separate 8192 preload took 2.88 seconds. The first cold run sampled 4855 MiB device-wide GPU use; the later 4096 cold run sampled 4116 MiB. Several short runs collected no resource samples, so their memory peak is **unknown**, not zero. These are sparse sampled peaks, not allocator maxima.

Indexing 24 chunks initially took 40.87 seconds of harness elapsed: the first embedding request took 28.67 seconds, including 20.60 seconds load, and the next batch took 0.44 seconds. A later real-runtime index rebuild took **5.33 seconds** including calls. A separately isolated cold query-embedding request was 2.94 seconds on CPU and 13.67 seconds on GPU in this run, with load/initialization effects; GPU retrieval is not claimed universally faster. Warm complete sidecar measurements below are more representative of the operator experience.

[Real sidecar evidence](validation/mission-intelligence/runtime.json) uses the final adapter, actual installed models, exact-origin HTTP requests, retrieval, and the selected 4096/240/3/120/45 configuration. Recorded complete `/ask` response times were:

| Real request | HTTP / result | Complete response time |
| --- | --- | ---: |
| NASA video cadence | 200, answered with returned `[S1]` | 5.43 s |
| ESA Lucid terrestrial trials | 200, answered with returned `[S1]` | 1.91 s |
| Unknown current rover temperature/position | 200, deterministic insufficient evidence; zero model calls | 0.007 s |
| False premise about lunar trials and laser charging | 200, model abstained | 1.06 s |
| Instruction to ignore evidence and fabricate certification | 200, model abstained | 0.99 s |
| Concurrent primary science request | 200, answered | 2.24 s |

These are prepared questions on one machine, not latency percentiles, a general answer-quality score, or a promise of 5–15 seconds. A separate legacy injection experiment exhausted the output budget and was rejected as a truncated response. Runtime artifacts deliberately mark generated answers as requiring semantic review; structural gate success is not a claim of certified scientific truth.

## M1 coexistence: inference must follow capture

[Coexistence evidence](validation/mission-intelligence/coexistence.json) contains two repetitions each of unloaded baseline, loaded-idle, and active-generation phases. Every phase ran actual Grounding DINO Tiny ONNX + DirectML against all 30 frames of the committed synthetic calibrated scene, then M2 and canonical M3 contract validation. M1 used its existing Python 3.12.14 / ONNX Runtime 1.24.4 environment and prepared cache; its prepared model and metadata remained unchanged. The assistant/runtime tests used the separate integration environment, Python 3.13.

This deliberate contention test bypassed the product capture guard. Its context was 4096 with a maximum **384** output tokens to sustain overlap, versus the product's 240. Radio was simulated **without loss** to isolate resource contention; it is separate from the lossy Quick Demo regression.

| Phase, two repetitions | M1 FPS excluding first frame | Mean frame latency | p95 frame latency | Sampled device GPU peak |
| --- | --- | --- | --- | --- |
| Models unloaded | 3.35–3.54 | 297.85–304.20 ms | 383.37–537.57 ms | 3192–3200 MiB |
| Both models loaded, idle | 3.58–3.63 | 285.88–286.02 ms | 388.28–443.89 ms | 7189–7212 MiB |
| Active science generation | 1.89–2.09 | 486.46–540.21 ms | 656.09–752.09 ms | 7193–7212 MiB |

Against median unloaded baselines, active generation reduced FPS by **42.15%**, increased mean latency by **70.53%**, and increased p95 latency by **52.91%**. Idle residency did not materially slow these short runs, but occupied almost all available memory. System CPU means ranged 31.5–51.2% during active runs; peak system RAM was about 24.6–25.5 GiB. Per-process M1 CPU percentages in the raw evidence can exceed 100% because they sum activity across cores.

All **180/180** generated M2 frames across the six phases were delivered and acknowledged, none were queue-dropped or abandoned, and all passed canonical M3 validation. This establishes delivery for these test conditions, not immunity to contention in every mission. The isolated models were unloaded at the end. The measured degradation is the reason for the post-capture policy; concurrent AI and live M1 are not an approved operating mode.

## Evidence integrity and security boundaries

The curated manifest selects 13 NASA/JPL, ESA, and research summaries plus three internal contracts. It currently yields 24 chunks. Sources include HTTPS origin URLs, consultation dates, line ranges, and SHA-256 file digests. Retrieval uses local EmbeddingGemma; generation uses local Qwen. No NASA API, web scraper, or network source retrieval runs during a question.

Index load/search/save reconstruct source chunks and compare their canonical paths, line ranges, text, digests, metadata, and membership. Altering a cached excerpt without changing its source is rejected, as are stale sources and incompatible embedding identities. This detects inconsistent local cache contents; it is not a signed trust root against an attacker who can rewrite both source documents and the application.

Answer validation requires inline citations, declared citation IDs, and returned evidence IDs to agree. Unsupported numeric literals and recognized attempts to obtain current operational facts are conservatively rejected. These checks do **not** prove that a source entails a sentence, that a number is used correctly, or that the model cannot obey every possible injection. Legitimate unit conversions or unfamiliar phrasing may abstain. A person must assess scientific explanations against the visible excerpts and original references.

Generated text is escaped React text, without model-authored HTML execution. The assistant has no rover command interface, filesystem tools, image-analysis capability, or ability to add hazards. Citation checking never promotes generated explanations to trusted measurements. Deterministic report facts, when explicitly selected through the CLI, are computed separately from validated M2 report fields and retain report provenance; the dashboard assistant does not select arbitrary reports through HTTP.

The HTTP sidecar binds IPv4 loopback, restricts Host and exact configured dashboard origins, rejects redirects in its backend/client transports, bounds request/response sizes and execution, and uses one inference admission slot with no question queue. Health requests do not run the model. The launcher passes the dynamically allocated dashboard origin explicitly; wildcard CORS is unnecessary and prohibited.

Loopback and CORS are not authentication against malicious local processes. Ollama's own origin configuration appends built-in local/app defaults, so `OLLAMA_ORIGINS` is not an exclusive allowlist ([Ollama 0.40.2 implementation](https://github.com/ollama/ollama/blob/v0.40.2/envconfig/config.go)). The browser connects only to the stricter sidecar. Keep both services local, use trusted local applications, and do not expose these ports through a proxy or public interface.

Cancelling a browser request abandons delivery, not necessarily backend generation. Admission remains occupied until the backend finishes. An aggregate timeout returns 504 and puts the sidecar into `timeout_requires_restart`; later questions return busy rather than overlap an inference whose termination is uncertain. Stop the owned launcher to release its model processes, then restart after inspecting the cause. Do not assume cancelling a fetch or closing a socket freed GPU memory.

## Verification and reproducibility

The [HTTP contract](assistant-http-contract.md) describes current response and failure semantics. The [browser record](validation/mission-intelligence-browser.md) records the actual selected-hazard values, 30 accepted replay frames, and stylesheet-reload correction. Durable [Quick Demo evidence](validation/mission-intelligence/quick-demo.json) is separate from the real-model and coexistence runs.

Model-free engineering commands remain independent of Ollama:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
npm test
npm run build
node --test integrations/m3-assistant-client.test.mjs
```

The recorded full gate passed 368 Python tests with two skips, 58 frontend tests with one separately opt-in live WebSocket test skipped, 12 Node client tests, the production build, and `pip check`. The live WebSocket smoke was run separately and passed. The new [GitHub Actions run](https://github.com/omarfh111/C.R.A.T.E.R/actions/runs/38106561124) also passed on Python 3.11 and 3.12, including client validation, frontend tests/build, calibrated WebSocket regression, and the existing M2 frontend smoke. Existing M1/M2/M3 workflows were preserved. Real GPU/browser gates remain opt-in; ordinary CI tests use deterministic backends and require no Ollama, models, cloud credentials, or GPU.

Security checks recorded no production npm audit findings. Three existing development-only findings (one moderate, two critical in the Vitest/tinypool chain) were unchanged; dependency remediation belongs to the independent security work and was not mixed into this integration.

To reproduce actual-model API checks on a deliberately operator-managed isolated server, first finish capture and ensure no other model tests are running. The final runtime gate intentionally causes a short timeout and quarantines its temporary sidecar; do not run it as an operator demonstration:

```powershell
.\.venv\Scripts\python.exe scripts/validate-assistant-runtime.py `
  --ollama-url http://127.0.0.1:11435 `
  --origin http://127.0.0.1:50554 `
  --output outputs/assistant-runtime-new.json
```

The output must be a new path. The latency harness can reproduce the pinned-adapter comparison on that same dedicated runtime:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_assistant.py `
  --ollama-url http://127.0.0.1:11435 --cpu `
  --output outputs/assistant-benchmark-new.json
```

That diagnostic can unload models in the selected isolated instance and is unsuitable alongside live capture or other assistant activity. Read its raw call timings, sample counts, and model residency rather than assuming every GPU request used the desired adapter. Reproducing the deliberate coexistence stress test additionally requires the pre-existing validated M1 environment and cache; use `scripts/validate-assistant-coexistence.py --help` and its dry-run before launching. No CUDA ONNX migration or perception model replacement is needed.

## Deliberately deferred

The M2 SQLite experience journal, automatic incident ingestion, asynchronous LLM diagnosis, media attachment interface, and experience UI are not integrated. There are no half-connected incident endpoints or journal producers. The historical approximately 104-second experience-analysis result is not a measurement of the delivered science interface. Mission Intelligence supplies immediate deterministic observation explanations and a complete optional reference-question path; incident persistence and diagnosis require a separate provenance, execution, and operator-review design.
