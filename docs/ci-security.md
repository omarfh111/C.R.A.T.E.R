# CI, browser verification and security hardening

This file documents the automated verification added on top of the existing M1, M2 and M3 CI.
It does not change the application, the validated AI pipeline, or the judge-facing Quick Demo:

```powershell
.\scripts\setup.ps1        # model-free environment
.\scripts\start-demo.ps1   # RECORDED ONNX REPLAY, no GPU, no model, no network
.\scripts\setup-gpu.ps1    # optional DirectML environment
.\scripts\start-live.ps1   # optional full live-AI demo
```

Nothing described here needs a GPU, ONNX weights, Ollama, an API key, a cloud service or a
repository secret.

## What runs, and when

| Workflow | Purpose | Triggers |
|---|---|---|
| `m1-tests.yml` | M1 perception reliability, M1→M2 contract, ONNX portability | existing |
| `m2-tests.yml` | M2 Python suite, benchmark, calibrated transport validation | existing |
| `mission-control-ci.yml` | Vitest, TypeScript build, M2 WebSocket live smoke | existing |
| `browser-e2e.yml` | Real Chromium against the real M2 bridge | PR to `main`, push to `ci/security-e2e` / `main`, manual |
| `codeql.yml` | Static analysis of Python, TypeScript and the workflows | the above, plus weekly |
| `security.yml` | Secret scanning, dependency audits, supply-chain review | the above, plus weekly |

Every workflow declares `permissions: contents: read` at the top level and widens it only where
a step genuinely needs more. Only `codeql.yml` requests `security-events: write`, and only for
the SARIF upload. `scripts/check-workflow-supply-chain.py` enforces that as a test.

## Browser verification (Milestone A and B)

```bash
npm ci
npx playwright install --with-deps chromium
python -m pip install -e .          # model-free M2 only
npm run test:e2e
```

Six checks run in about 90 seconds, one worker at a time, in `tests/browser/`:

1. **The recording under test** is the committed 30-frame calibrated ONNX capture, sequences
   0–29, one rover.
2. **LIVE mode, intro, full replay.** The cinematic intro plays and hands off, the dashboard and
   all panels appear, the `SOURCE` chip reads `LIVE`, the MOCK `DEMO` control is absent, and
   Mission Control's own `ACCEPTED` counter reaches **30** with `INVALID`, `DUPLICATE`,
   `OUT-OF-ORDER` and `SEQ GAPS` all at 0 and the latest sequence at 29. The displayed rover
   ENU, uncertainty, hazard positions, hazard uncertainty and observation clock are compared
   against the frames M2 actually delivered, read from its `--received-jsonl`.
3. **Hazard selection and inspection.** Selecting an inventory row fills the inspector, sets
   `aria-pressed`, and `CENTER ON MAP` moves the map so that the map's own inverse projection,
   read back from the cursor readout, reports the hazard's actual M2 coordinates. `Esc` clears.
4. **Responsiveness** at 1600×1000, 1280×800 and 390×844, asserting the map keeps a usable box
   and no viewport introduces horizontal page overflow.
5. **Simulated radio blackout.** With a 12-second blackout inside M2's radio simulation, the
   dashboard is sampled atomically about four times a second for the whole replay. The suite
   asserts a hold of more than six seconds during which the accepted count, the sequence and
   the ENU readout do not move, that the WebSocket stayed `CONNECTED` throughout, that the
   posture never claimed `TRANSPORT DOWN`, that the fix was labelled `LAST KNOWN POSITION` and
   `STALE` for the whole hold, and that retransmitted frames afterwards advance the sequence and
   the position to 30/30.
6. **Station loss.** Killing M2 mid-mission flips the posture to `TRANSPORT DOWN` with
   "Station connection lost" and "radio state is unknown", logs `STATION DOWN`, and freezes the
   last accepted fix instead of extrapolating it.

### Design decisions worth knowing

- **M2 delivering 30/30 is not evidence that M3 accepted 30.** Every count assertion reads
  Mission Control's own `PACKET ACCOUNTING` panel. M2's report is checked separately, as a
  second, independent claim.
- **No mocked telemetry.** Each test spawns the real `python -m crater_m2` against
  `examples/m1-onnx-calibrated/observations.jsonl`. No browser-side telemetry is injected and
  no hazard frame is invented.
- **Historical timestamps stay historical.** The recording was captured in the past, so the
  dashboard correctly shows `STALE` and an information age in the tens of thousands of seconds.
  The suite asserts that, rather than expecting fabricated freshness.
- **Readiness probes, not sleeps.** A station is considered up only once M2 prints
  `M2 station ready` on stdout, and the page is opened only after that, so the dashboard's
  WebSocket is the connection that releases M2's `--wait-for-client` gate.
- **The production bundle, not the dev server.** `npm run dev` runs React in development mode,
  where `StrictMode` mounts the telemetry adapter twice and closes the first WebSocket; M2's
  gate releases on that first connection, which adds an avoidable race to the first frames.
  The suite builds and serves the production bundle with `vite preview`, so there is one
  adapter, one socket and one deterministic sequence — and the bundle that actually ships is
  what gets verified. `scripts/start-demo.ps1` is untouched and still uses the dev server; its
  deliveries begin after the simulated blackout, long after the StrictMode remount.
- **Isolated loopback ports.** `CRATER_E2E_WEB_PORT` (default 4318) and `CRATER_E2E_WS_PORT`
  (default 8799) both differ from the demo's 5173/8765, so an interactive demo session and this
  suite never compete. LIVE mode and the WebSocket URL are passed to Vite through the process
  environment, so `.env.local` is never written.
- **Bounded.** 150 s per test, 8 minutes for the whole suite, 12 minutes for the CI step.
  Failures upload the Playwright HTML report, traces, screenshots, the JUnit summary and each
  M2 station's stdout, delivered-frame JSONL and run report.

`CRATER_E2E_PYTHON` overrides the interpreter; by default the suite uses `.venv` when present
and falls back to `python`.

## CodeQL (Milestone C)

`codeql.yml` analyses `python`, `javascript-typescript` and `actions`, all with
`build-mode: none`, so no model, runtime or GPU package is installed to analyse them.
`.github/codeql/codeql-config.yml` excludes only generated output (`dist`, `node_modules`,
`test-results`, `playwright-report`) and the committed evidence data in `examples`. Test code is
analysed, not excluded.

The `analyze` step succeeds whatever it finds, so the gate is a separate step: any result CodeQL
rates as an error, or with a security severity of 7.0 or above, fails the job; everything else
is annotated and tabulated in the job summary as advisory. Results are never suppressed to keep
the job green.

### Finding investigated and fixed

- **`py/http-response-splitting` at `crater_assistant/server.py:54`** — real, and fixed.
  `allowed_origin()` parsed the request's `Origin` header with `urlsplit()`, which removes ASCII
  tabs and newlines *before* parsing. A folded header such as
  `Origin: http://127.0.0.1:51<CRLF><TAB>73` therefore satisfied every parsed check, and the raw
  value was echoed into `Access-Control-Allow-Origin`, putting attacker-controlled CRLF into the
  response header block. Reproduced end to end over a raw socket before changing anything.

  The fix compares the whole header against a tuple of exact literals and echoes the matching
  *literal*, never the request's own bytes, so no client-supplied text can reach a response
  header. All six local dev-server origins (`localhost`, `127.0.0.1`, `[::1]` on 5173 and 4173)
  still work. `tests/test_assistant.py` adds 14 regression tests, including the raw-socket
  injection attempt; six of them fail against the previous implementation.

  This is a loopback-only sidecar for a future M3 panel. It is not part of the M1/M2/M3
  pipeline, and the Quick Demo is unaffected.

## Security and dependency audits (Milestone D)

### Secret scanning

TruffleHog (pinned by tag *and* digest) scans every commit reachable from the ref, from a full
clone rather than a shallow one, and then scans the built Vite bundle so a mistyped `VITE_*`
variable cannot publish a credential to every visitor.

`scripts/summarize-trufflehog.py` applies the policy and writes the report:

| Classification | Meaning | Policy |
|---|---|---|
| `verified` | the provider confirmed the credential is live | **blocking** |
| `unknown` | verification could not complete | **blocking**, except the generic `URI` detector |
| `unverified` | the provider rejected the pattern | advisory |

Only metadata is ever printed — detector, classification, path, line, commit. The matched text
is never written to a log, an annotation or the job summary, and git history is never rewritten
from CI.

**Baseline:** 0 verified secrets. One `unknown` `URI` match, at `tests/test_assistant.py:98`:
the hostile URL `http://127.0.0.1:11434@evil.org` used as a negative test fixture asserting that
the assistant refuses it. The generic `URI` detector matches any `scheme://userinfo@host` shape
and cannot identify a provider-specific credential, which is why its unverifiable hits are
advisory; it is still listed, so nothing is hidden. Every other detector blocks on `unknown`.

### npm

| Check | Policy |
|---|---|
| `npm audit signatures` | blocking |
| `npm audit --omit=dev --audit-level=high` | blocking |
| `npm audit` (full tree, all severities) | advisory |

**Baseline:** registry signatures verified for all 181 packages, 86 with provenance
attestations. **Production dependencies: 0 vulnerabilities.**

Documented dev-tooling baseline, reported and not hidden:

- `tinypool` ≤ 2.1.1 — critical, prototype-pollution to RCE through worker options.
- `@vitest/mocker` — moderate, path traversal through a redirect mock.

Both arrive through `vitest@3.2.7`, which pins `tinypool@^1.1.1`. No 1.x fix exists, and 3.2.7
is the newest 3.x, so the only remedy npm offers is `vitest@5`, a breaking major upgrade of the
runner the M3 suite is validated against. Neither package reaches the shipped browser bundle,
and the attack requires control of the test runner's own worker options, which only this
repository's configuration supplies. The lockfile is therefore left alone and the advisory is
recorded here. Revisit when vitest 5 is adopted deliberately, with the Vitest suite re-validated.

### Python

Three clearly separated sets, because they have very different exposure:

| Set | Contents | Installed in CI | Policy |
|---|---|---|---|
| core runtime | `numpy`, `websockets`, `opencv-python-headless`, `pillow`, `psutil`, `scipy` | yes, resolved environment | blocking when a fix exists |
| optional model-free extras | `pypdf`, `requests`, `python-dotenv`, `gradio-client`, `huggingface-hub`, `pytest` | yes, resolved environment | advisory |
| local ONNX group | `torch`, `transformers`, `onnx`, `onnxruntime`, `onnxruntime-directml` | **no** | advisory |

The local ONNX group is audited without being installed. `scripts/pin-python-deps.py` reads
`pyproject.toml`, evaluates the environment markers for a chosen `sys_platform`, and resolves
each requirement to the newest release that satisfies it from the PyPI JSON metadata API. The
resulting pins go to `pip-audit --no-deps`. Nothing is downloaded, built or installed, so no GPU
package lands on a runner, and both halves of the marker split — the portable CPU runtime and
the Windows DirectML provider — are audited from one Linux job.

`scripts/summarize-pip-audit.py` de-duplicates pip-audit's per-alias repeats and applies the
policy.

**Baseline:**

- **core runtime: 0 known vulnerabilities.**
- optional model-free extras: `pypdf`, `requests`, `python-dotenv`, `gradio-client` and
  `huggingface-hub` clean.
- `pytest` was pinned `>=8,<9`, which excluded the fix for CVE-2025-71176 / PYSEC-2026-1845
  (local tmpdir handling on UNIX, fixed in 9.0.3). `requirements-m1.txt` already allowed 9.x, so
  the `test` extra is now `>=8,<10`. Validated: the full Python suite passes on both 8.4.2 and
  9.1.1.
- local ONNX group: **15 advisories, none actioned by design.** `onnx==1.20.1` carries eight
  (fixes in 1.21.0 / 1.22.0) and `transformers==4.57.1` carries seven, three of which have no
  fixed release at all. `torch` is clean at the version the range resolves to.

  These pins are deliberate: they are the versions the calibrated ONNX evidence bundle and its
  SHA-256 manifest were produced with. Upgrading ONNX Runtime, Transformers or PyTorch would
  invalidate that evidence and risk the validated DirectML pipeline, so it is **not** done
  speculatively here. None of these packages is installed by `scripts/setup.ps1`, by
  `start-demo.ps1` or by the default CI — only by the opt-in `setup-gpu.ps1` / `start-live.ps1`
  path. Any upgrade belongs in a dedicated change that re-runs the calibration and regenerates
  the manifest.

### Supply chain

`scripts/check-workflow-supply-chain.py` reviews every workflow definition and fails on:

1. `pull_request_target` or `workflow_run`, which run pull-request code with the base
   repository's secrets and a write-capable token;
2. a missing top-level `permissions` block;
3. `contents: write`, `packages: write`, `id-token: write`, or `security-events: write` outside
   `codeql.yml`;
4. `${{ github.event.* }}`, `github.head_ref`, `github.ref_name` or `inputs.*` interpolated into
   a `run:` script, which is shell injection;
5. a third-party action on a mutable reference — anything outside `actions/` and `github/` must
   be pinned to a full 40-character commit SHA;
6. a repository secret read by a `pull_request`-triggered workflow.

**Baseline: all six workflows pass.** No workflow reads a secret, none uses a privileged
pull-request trigger, every one pins its permissions, and the only third-party dependency is the
TruffleHog container, pinned by digest.

## Known limitations

- `tests/test_bridge.py::test_actual_websocket_one_canonical_json_per_message` can time out its
  WebSocket opening handshake on a heavily loaded machine. Observed once locally under
  contention and not reproducible on re-run; pre-existing, and not addressed here.
- The browser suite verifies rover and hazard geometry through the numeric readouts and the
  map's own inverse projection. It does not compare rendered map pixels against a reference
  image, which would be brittle across platforms.
- Code Scanning upload is gated on repository visibility, so on a private fork without GitHub
  Code Security the CodeQL gate reads the SARIF in the job instead of uploading it.
