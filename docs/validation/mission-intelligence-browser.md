# Mission Intelligence browser and stylesheet regression

Validation date: 2026-10-11. Branch: `feat/m2-assistant-integration`.
The source revision before the scanner correction was
`84dbb19d36b14af7f1e88d45609d4a901a0c482d`; the verified correction is the
one-line `src/style.css` import shown below. Commit identity is recorded in the
branch history rather than treating a working-tree validation as an existing commit.

## Verified development-server defect

Early browser rehearsals restarted the application during replay even though
Mission Intelligence components were frozen. One rehearsal retained only the
last 29 accepted frames, sequences 1–29, although M2 delivered all 30.

The reload timestamps matched backend-file writes exactly:

| Backend file | File modification, UTC | Browser full reload, UTC |
| --- | --- | --- |
| `scripts/benchmark_assistant.py` | 02:32:44 | 02:32:44 |
| `scripts/validate-assistant-coexistence.py` | 02:35:13 | 02:35:13 |

Inspection of the installed Vite 7.3.7 and Tailwind Vite plugin established the
mechanism. `@import "tailwindcss"` enables project-wide source scanning. The
Tailwind plugin registers scanned files as stylesheet dependencies; its
`hotUpdate` handler explicitly sends a full reload for changed non-JavaScript,
non-CSS dependencies. The Python files were among these sources. This was not
a telemetry schema or reducer defect. Generated artifacts were not established
as the trigger and are not presented as its cause.

The correction restricts utility scanning to the frontend source directory:

```css
@import "tailwindcss" source("./");
```

The path is relative to `src/style.css`. Frontend files remain eligible for
normal development updates. Backend code, validation scripts, documents, and
runtime artifacts no longer contribute Tailwind candidates or dependencies.
No Vite watcher ignore list, telemetry code, WebSocket protocol, or demo
launcher was changed for this correction.

## Production appearance and automated checks

After the correction, the production build passed and the full frontend suite
passed **58 tests**, with the separately invoked live WebSocket smoke test
skipped in that run. Its skipped status is not counted as a successful smoke.

Compiled CSS decreased from **52,632 to 52,389 bytes**. All handwritten Mission
Control, Mission Intelligence, lunar intro, dashboard, body, and font-face rules
compared unchanged. The only removed selectors were unused standalone Tailwind
utilities: `.contents`, `.grow`, `.inline`, `.relative`, `.rounded`, `.table`,
`.truncate`, and `.visible`. No selectors were added. Frontend source inspection
confirmed these were not assigned standalone class names; `is-visible` remains
a separate intro class.

Local comparison evidence is in
`artifacts/vite-watch-validation/comparison.json`. These files are generated
validation output, not required application inputs.

## Actual browser rehearsal after the correction

The fourth fresh Quick Demo rehearsal used
`http://127.0.0.1:50554/`. The browser showed **ACCEPTED 30**, covering sequences
**0–29**. The original historical timestamps remained visible. Mission Control
continued to show those 30 accepted frames when the optional local assistant
was unavailable.

The root agent selected hazard `000001` and checked the inspector against the
accepted values:

| Displayed quantity | Value |
| --- | --- |
| Local ENU position | E −0.98 m, N 3.95 m, U 0.00 m |
| Detector confidence | 0.68 / 1.00 |
| Transmitted uncertainty radius | 0.11 m |
| Horizontal distance from latest rover fix | 3.79 m |

The deterministic explanation preserved the distinction between detector
confidence and location uncertainty, historical capture age and recent receipt,
and rover link counters and station connection state. LIVE identified the
WebSocket connection, while the Quick Demo provenance described historical
ONNX detections from a synthetic calibrated scene and simulated radio effects.

The root agent visually reviewed the real browser screenshot and reported no
browser errors in this rehearsal. This record does not claim that citation
identity certifies scientific truth or that the generated assistant text is
trusted telemetry. Real-model answers and coexistence measurements are recorded
separately.

## Actual optional GPU assistant in the browser

The root agent also exercised the optional launcher under Windows PowerShell
5.1, using its isolated Ollama endpoint `http://127.0.0.1:11436` and assistant
HTTP sidecar `http://127.0.0.1:8766`. The launcher used the explicitly allowed
dynamic dashboard origin. Loaded-model evidence showed Qwen3 4B occupying
approximately **3,030.9 MiB of GPU memory**; this is model residency, distinct
from sampled total device-memory peaks in the benchmark evidence.

A real NASA science answer appeared in Mission Intelligence. Its generated
text cited **S1 and S2**. Three evidence passages were returned; S3 remained
uncited rather than being presented as a used citation. The root agent opened
S1 and visually checked its source excerpt, official NASA URL and SHA-256
metadata. The unverified generated-text label and separate deterministic
mission facts remained visible.

An operator question asking for the current battery voltage and exact crater
distance returned **INSUFFICIENT EVIDENCE**, with **zero sources** and no LLM
call. The browser retained **30 accepted telemetry frames** throughout these
assistant interactions. No generated explanation became a hazard or trusted
mission measurement.

The locally reviewed screenshot is
`<user-home>/.codex/visualizations/2026/10/11/01a128ae-764d-7e21-a701-fb4445cecbfc/mission-intelligence-gpu-answer.jpg`.
It is a local review artifact, not a durable repository attachment or a
portable screenshot link. Durable numeric results, returned answers and model
digests are preserved in the [measurement evidence bundle](mission-intelligence/README.md).

The first attempted browser cancellation did **not** establish a cancellation
pass: the request encountered BUSY, and source inspection by the launcher's
live-M1 protection then produced a false positive. The root agent scheduled a
retry after correcting that guard. This record does not claim the browser
cancellation succeeded. The separate real HTTP disconnect/cancellation harness
passed its recorded gate in [runtime.json](mission-intelligence/runtime.json);
that result does not substitute for the unfinished browser interaction. Client
cancellation still does not guarantee termination of backend inference.


## Corrected launcher, fresh checkout and final browser checks

After the capture-guard fix, Windows PowerShell 5.1 successfully launched the
real GPU sidecar for the fresh demo origin `http://127.0.0.1:51796`. The browser
started generation, accepted CANCEL REQUEST, displayed CANCELLED with the
backend-may-continue limitation, and retained all 30 accepted frames. The client
required a new connection before asking again. This completed the previously
unfinished browser cancellation check. A subsequent actual NASA stereo-camera
answer displayed S1/S2 citations and three returned passages beside hazard
000001. No browser console errors were recorded in this fresh-demo tab.

The existing responsive layout was tested at 390 by 844 pixels: the tactical
map and inspector remained accessible, the panel fitted within the viewport
without horizontal overflow, and the viewport override was reset afterward.
The final reviewed screenshot is [mission-intelligence.jpg](mission-intelligence/mission-intelligence.jpg).

The fresh archived checkout used only the original base setup. ONNX Runtime,
PyTorch, Transformers and pypdf were absent, the Ollama executable was hidden
from PATH, and its configured endpoint was unavailable. The original launcher
delivered 30/30 with original timestamps, 25% simulated packet loss and the
0.5–5 second blackout followed by recovery. The browser accepted 30 with zero
invalid, duplicate or out-of-order frames. See [quick-demo.json](mission-intelligence/quick-demo.json).

Finally a harmless owned `start-live.ps1` sleeping process exercised the actual
launcher safeguard: the owned GPU server and HTTP sidecar closed, while the
shared Ollama listener remained unchanged. This is a process-guard regression,
not a simultaneous capture measurement; [launcher-guard.json](mission-intelligence/launcher-guard.json)
records that distinction. Real M1 contention is measured separately.

Manual review does not establish semantic correctness of all generated prose.
For example, the final stereo-camera answer added crater/cliff examples beyond
the literal list in its cited summary. These remain unverified generated science
context; the visible source excerpt and original reference need review. No such
prose or examples were accepted as rover observations or mission facts.
