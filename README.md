# C.R.A.T.E.R.

## Start Here

**Windows prerequisites:** PowerShell, Python 3.12+, Node.js 24+ with npm, and a browser.

```powershell
git clone --branch feat/end-to-end-integration https://github.com/omarfh111/C.R.A.T.E.R.git
cd C.R.A.T.E.R
```

**Quick Demo (recommended; no GPU, model download, secrets, or AI service):**

```powershell
.\scripts\setup.ps1
.\scripts\start-demo.ps1
```

**Full Live AI Demo (optional; compatible Windows DirectML GPU):**

```powershell
.\scripts\setup-gpu.ps1
.\scripts\start-live.ps1
```

The launcher opens Mission Control and prints its local `http://127.0.0.1:<port>/` URL. Each run uses fresh loopback ports to keep older tabs from triggering capture. Quick Demo is **RECORDED ONNX REPLAY**: its 30 predictions came from an earlier real ONNX run, while M2's binary radio simulation, WebSocket bridge, and M3's LIVE telemetry view run now. Radio loss and blackout are simulated; original capture times stay historical. Full Live AI runs fresh pixel-derived ONNX inference from the committed calibrated video. First-time GPU setup may require substantial downloads.

If Windows blocks scripts, run `Set-ExecutionPolicy -Scope Process Bypass` in that PowerShell window, then retry; this does not change the permanent policy. See the [technical launch guide](docs/end-to-end-integration.md), [ONNX evidence bundle](examples/m1-onnx-calibrated/README.md), and [seven-minute demo guide](docs/seven-minute-demo.md).

This integration branch combines local rover perception (M1), calibrated spatial
telemetry (M2), and the Mission Control dashboard (M3). The Python modules and
React frontend share one checkout. Model inference and the WebSocket bridge run
locally; the dashboard consumes canonical JSON frames in LOCAL_ENU_V1.

## Modules and contracts

- M1: `crater_m1/`, [perception contract](docs/m1-contract.md), and
  [calibrated ONNX validation](docs/m1-final-validation.md).
- M2: `crater_m2/`, [spatial and radio guide](M2_README.md),
  [ONNX callback integration](docs/m1-m2-onnx-integration.md), and
  [calibrated handoff](docs/m1-calibrated-handoff.md).
- M3: `src/`, [telemetry contract](docs/telemetry-contract.md),
  `package.json`, and `src/telemetry/contract.ts`.
- The optional local assistant remains documented in [ASSISTANT_README.md](ASSISTANT_README.md).
  Hosted M1 experiments remain optional and do not satisfy the local-only demo.

## End-to-end integration

- [Windows setup and launch guide](docs/end-to-end-integration.md)
- [Measured validation evidence](docs/integration-validation.md)
- [Seven-minute live demonstration](docs/seven-minute-demo.md)

## Development checks

Use the setup scripts above for a fresh clone. The Python test suite does not
download model weights; hardware validation is a separate local run.

```powershell
& .\.venv\Scripts\python.exe -m pip install -e '.[test,hosted,spaces]'
& .\.venv\Scripts\python.exe -m pytest -q
npm test
npm run build
```

The launchers configure ignored `.env.local` for LIVE telemetry and print the
selected local URL. For manual development, M2 defaults to
`ws://127.0.0.1:8765/telemetry`; copy `.env.example` to `.env.local` and set
`VITE_TELEMETRY_MODE=LIVE` before running `npm run dev`.
The frontend defaults to deterministic MOCK mode until LIVE is selected.
M3 validates every received frame and preserves the last accepted state
through radio delays and WebSocket reconnects. Restart a browser telemetry
session when M2 sequence numbering restarts, or use an increasing
`--start-sequence`.

The cinematic lunar introduction and dashboard are local assets. The map
uses accepted LOCAL_ENU_V1 coordinates and is not surveyed lunar imagery.
A station WebSocket disconnection does not establish a rover radio blackout.
Stale age is based on capture time; historical observation replay can
legitimately remain stale.

Calibrated synthetic-scene ONNX results validate this controlled pipeline,
not real lunar mapping. The NASA videos lack matching calibration and their
available annotations do not match the supplied video hashes.
