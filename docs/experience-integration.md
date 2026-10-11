# Optional post-capture incident dialogue

This extension records bounded, explicit robot incidents independently of Ollama and attaches optional science explanations after capture. It selectively adapts the journal/worker ideas at M2 `57b29439ced649fc5ca9bb39918beef2aa387c83` to the protected assistant on main `1d38cade9a8408e30141d92e8ec23e158836654c`. Old assistant files were not substituted. The canonical WebSocket v1 schema, radio/codec, accepted hazards, DirectML implementation and default launch commands retain their behavior.

## What becomes automatic

After the operator connects the journal and selects the actual producer session in **Mission Intelligence → ROBOT INCIDENT DIALOGUE**, the dashboard records changes in WebSocket transport, the radio state declared by accepted frames, stale receipt/capture evidence, and available invalid/out-of-order/sequence-gap warnings. These are separate incident types. A 30-second per-kind/key cooldown and durable server deduplication prevent a question per image. Initial counters establish a baseline rather than attributing previous-session warnings to a new capture.

M2 additionally records its actual geometry rejection or producer exception warnings through a bounded native writer. Missing frames never imply calibration or tracking failure. A healthy real DirectML clip produced no such warnings. Specific tracking diagnostics remain deferred until the producer exposes an explicit event; the collector does not invent their cause.

Every saved incident has a UUID, native session/rover identity, trigger/record/capture/receipt timestamps where available, explicit provenance, an optional complete validated v1 snapshot, and a server-chosen question. A decision is stored only if explicitly supplied. Browser reports are labelled `dashboard-client-reported-v1`, with `certifiedMeasurement: false`. Native provenance is `synthetic`, `historical_replay`, or `live_inference`; the radio remains simulated. LIVE denotes WebSocket connectivity, not fresh inference.

The producer closes its session only after capture/producer shutdown and radio/report cleanup. The worker then automatically schedules saved questions when the guarded sidecar is available. **Launching the optional model remains an explicit operator action after capture.** A producer crash without a completion marker requires explicit recovery; silence does not end capture. Completed sessions have a short closing window for stale/disconnection events, then stop collecting. New observations cannot be attached to an ended or different-rover session. Manual science questions remain separate from automatic incident requests.

## Windows: unchanged default demo

```powershell
Set-Location D:\space_esb_mission_dialogue
.\scripts\setup.ps1
.\scripts\start-demo.ps1
```

No journal, model, GPU or Ollama service is required by these two commands. The default dashboard performs no journal requests until activated. The following steps are optional; they add no dependency or model download to Quick Demo.

## Windows: collect now, analyze after capture

Use separate PowerShell windows in the same checkout. Choose one absolute database path and use it for M2, the collector, and the assistant. The environment variable is local to the terminal that launches M2; set it **before** capture:

```powershell
Set-Location D:\space_esb_mission_dialogue
$env:CRATER_INCIDENT_JOURNAL = Join-Path (Get-Location) 'outputs\mission-incidents.sqlite3'
.\scripts\start-demo.ps1
# Or launch the existing real-GPU flow from this terminal after its ordinary setup.
```

Use the **actual dashboard origin printed by the launcher**, without a trailing slash, in another terminal:

```powershell
Set-Location D:\space_esb_mission_dialogue
$origin = 'http://127.0.0.1:56215' # replace with the printed dynamic origin
$db = Join-Path (Get-Location) 'outputs\mission-incidents.sqlite3'
.\.venv\Scripts\python.exe -B -m crater_assistant.journal `
  --database $db --port 0 --allow-origin $origin
```

Port `0` chooses an available loopback port and prints it. On the target PC, port 8767 was excluded by Windows; using an allocated port avoided changing OS policy. Enter the printed collector URL in Mission Intelligence, select **CONNECT JOURNAL**, then select the session matching the current rover and capture. Selection is explicit to avoid mixing captures of the same rover. Reconnect if the collector was initially empty; select each new native session. Start this before incidents of interest; an inactive or closed browser cannot retrospectively create transport/staleness events. The fast default replay may finish before activation; use the slower optional walkthrough below for a visible demonstration.

Once capture has finished, start the existing protected assistant against the **same** database:

```powershell
Set-Location D:\space_esb_mission_dialogue
.\scripts\start-assistant.ps1 `
  -DashboardOrigin 'http://127.0.0.1:56215' `
  -JournalPath 'outputs\mission-incidents.sqlite3'
```

This uses the already installed Qwen3/EmbeddingGemma models, an owned isolated Ollama at 11435 and sidecar at 8766. Shared Ollama at 11434 is untouched. The collector defaults to this sidecar; if choosing another assistant port, pass its exact URL with `--assistant-url` when starting the collector. All browser origins must be explicitly configured; there is no wildcard CORS. Multiple exact origins may be provided by repeating `--allow-origin`.

The journal remains usable when Ollama is off. Jobs show **WAITING FOR LOCAL AI** until readiness and the capture gate allow admission. Sidecar HTTP readiness, model availability and busy generation remain distinct. Startup may require model loading/kernel preparation; perform it outside the seven-minute rover demonstration. Close the owned assistant launcher with Ctrl+C before another live M1 capture. The independent collector may remain running.

Remove the optional producer setting when finished:

```powershell
Remove-Item Env:CRATER_INCIDENT_JOURNAL
```

### Slower historical walkthrough used for browser validation

Keep a LIVE dashboard configured for the chosen WebSocket port open, start the collector with its exact frontend origin, then run this from the model-free environment. This optional test uses the existing committed historical ONNX observations and simulated radio, not fresh perception:

```powershell
.\.venv\Scripts\python.exe -B -m crater_m2 `
  --input examples/m1-onnx-calibrated/observations.jsonl --input-ground-z 0 `
  --duration 35 --drain 60 --fps 1 --bandwidth 4096 --latency .005 --jitter 0 `
  --loss .25 --blackout 2:10 --queue 128 --attempts 20 --seed 7 `
  --port 56216 --wait-for-client 120 `
  --incident-journal outputs/mission-incidents.sqlite3 `
  --report outputs/incident-replay.json --received-jsonl outputs/incident-frames.jsonl
```

Use the actual dashboard WebSocket port; 56216 is the validation example. For successive runs in one dashboard session, use `--start-sequence` above its last accepted sequence or reload the dashboard. Select the newly created producer UUID. The original launchers continue to allocate ports dynamically.

## Persistence, bounds and recovery

SQLite uses WAL, FULL synchronization and short transactions. Default limits: 10,000 incidents/sessions/reviews each, 16 active jobs, one worker per database enforced by an OS lease, three admitted model attempts per incident, and a one-hour automatic availability window from recording/retry. A saturated analysis queue still saves the incident as **QUEUE FULL · INCIDENT SAVED**. The operator can retry after capacity is released. No silent pruning occurs; export and archive deliberately before storage capacity is exhausted.

The producer's warning handoff is bounded at 16 and nonblocking during capture. The report exposes recorded/dropped/failed counts; optional journal failure never stops telemetry. This is bounded best-effort warning collection, not a guarantee that every warning survives queue/storage failure. Native shutdown flushes before the completion marker.

The browser outbox persists up to 32 unsent UUID events per collector/session in localStorage. Delivery pauses after rejection or three attempts, retaining pending events for explicit **RETRY PENDING EVENTS**. Refresh of sessions/jobs continues even with a rejected queue head. Browser storage can be denied or lost; the panel reports the limitation. A full outbox cannot preserve additional events. The HTTP incident list displays the latest 20 records globally, sessions the latest 20, and reviews the latest 10 per incident; export contains the complete bounded journal.

Service unavailability does not consume a model attempt before admission. Busy/availability retries back off 10 seconds; expiry requires explicit retry. A restarted worker marks in-flight work **INTERRUPTED** and retains an attempt audit record, requiring explicit retry instead of silently repeating a potentially completed generation. Completed results are not overwritten by retry. **CANCEL JOB** stops queued work; an admitted request may continue until the bounded backend deadline. Its attempt remains auditable, and cancelled output is not promoted into the incident's displayed result.

After a producer crash, first verify capture has stopped, then explicitly close its interrupted session:

```powershell
.\.venv\Scripts\python.exe -B -m crater_assistant.journal `
  --database outputs/mission-incidents.sqlite3 --finish-interrupted-session 'PASTE-SESSION-UUID'
```

The command refuses active or indeterminate M1 capture. It makes queued analysis eligible only through the ordinary guarded worker.

Export to a new file; the command refuses overwriting an existing export:

```powershell
.\.venv\Scripts\python.exe -B -m crater_assistant.journal `
  --database outputs/mission-incidents.sqlite3 --export outputs/incident-export.json
```

Reviews (`confirmed`, `rejected`, `inconclusive`) are separately stored operator-reported notes. Even a confirmed review never changes accepted telemetry or imports generated material into RAG. No rover command or driving decision is generated automatically.

## Evidence and security boundaries

The collector uses the existing bounded HTTP transport, exact loopback Host/origin validation, 16 KiB request limit and at most eight admitted connections. Worker HTTP refuses proxies/redirects and unsafe hosts, bounds responses to 512 KiB and uses an aggregate 50-second deadline; sidecar generation retains its aggregate 45-second deadline and single inference slot shared with manual questions. Health remains responsive. These are same-user loopback tools, not authenticated multi-user services: local processes and users with filesystem access can inspect or alter the database. CORS does not authenticate native clients. Keep files private with normal Windows account permissions; no database encryption is provided.

Only incident identity crosses the worker/sidecar API; both read the configured journal. The model receives bounded untrusted context and availability flags, not coordinates, telemetry numbers or image bytes. Context is not a scientific source or deterministic fact. Existing source/index digests, citation identity, malformed-response, numeric and operational-fact controls remain. Additional conservative filters abstain on tested timestamp contradictions and claims of image interpretation. These filters may reject useful wording and do not prove semantic truth or resist every possible prompt injection. Returned prose is always **UNVERIFIED GENERATED EXPLANATION**; inspect cited excerpts before using it. No generated text enters canonical telemetry state or accepted hazards.

### Image references: preparation only

With a fixed `--media-root` configured on the collector, an incident may contain up to four local PNG/JPEG references with a relative path, matching SHA-256 and explicit `synthetic`, `historical_replay`, `live_capture` or `operator_supplied` provenance. Absolute paths, traversal, symlink escape, wrong hashes, malformed images, files over 5 MiB and excessive dimensions are rejected. References record `imageAnalysis: not_performed`; no image endpoint, automatic image capture, image-to-incident association, image upload or vision model is implemented. A local file owner could later change a file; the recorded hash is a reference-time integrity check, not immutable storage. Multimodal interpretation remains a subsequent, separately benchmarked stage.

## Reproducible validation

The target-PC results, model digests, generated answers, separate reviews and test conditions are in [the evidence report](validation/incident-dialogue/evidence.md). Ordinary CI remains offline and model-free:

```powershell
python -m pytest -q
npm test
npm run build
node --test integrations/m3-assistant-client.test.mjs
node scripts/validate-m3-contract.mjs src/telemetry/contract.ts outputs/incident-frames.jsonl
```

The dedicated assistant workflow runs on main, feat/** and codex/**, with full Python/frontend/client checks, real model-free WebSocket regression, and a Windows journal job. Real GPU tests are explicit target-PC checks, not CI prerequisites.

To reproduce live M1 validation, use the already validated M1 Python/cache without installing or modifying it:

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& D:\space_esb_m1\.venv\Scripts\python.exe -B -m crater_m2.validation `
  --output outputs/new-directml-validation --m3-contract src/telemetry/contract.ts -- `
  --perception-video examples/m1-onnx-calibrated/scene.mp4 `
  --calibration examples/m1-onnx-calibrated/calibration.json `
  --device directml --cache-dir D:\space_esb_m1\.cache\huggingface `
  --max-frames 30 --no-preview --duration 60 --drain 30 --fps 50 `
  --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:5 `
  --queue 128 --attempts 20 --seed 7 --incident-journal outputs/live-incidents.sqlite3
```

A separate opt-in script tests the live capture guard with six real DirectML frames while the owned assistant is initially idle; the launcher is expected to shut down its own GPU processes:

```powershell
.\.venv\Scripts\python.exe -B scripts/validate-incident-dialogue.py `
  --output outputs/new-guard-validation `
  --m1-python D:\space_esb_m1\.venv\Scripts\python.exe `
  --cache D:\space_esb_m1\.cache\huggingface
```

After capture, with the guarded owned assistant ready, evaluate real incident context using its printed index path and a new output path:

```powershell
.\.venv\Scripts\python.exe -B scripts/validate-incident-dialogue-ai.py `
  --database outputs/mission-incidents.sqlite3 `
  --index outputs/assistant-PASTE-RUN/research-index.json `
  --output outputs/new-dialogue-ai.json
```

It requires a saved stale incident with an observation, checks native capture inactivity, evaluates NASA context, unknown live measurements and injected context, and records actual Ollama load/prompt/generation timings, residency and a VRAM snapshot. A snapshot is not a measured memory peak. CPU/first-CUDA-startup timings and concurrent M1 generation were not re-benchmarked in this stage. The existing approximately 42% concurrent M1 throughput loss remains the reason for sequential capture/analysis; no concurrent-performance claim is made here.
