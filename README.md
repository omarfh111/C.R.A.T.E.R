# C.R.A.T.E.R.

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

## Development checks

Windows prerequisites: Python 3.11+ and Node.js 24. Reuse the validated local
ONNX DirectML model cache when running inference. The Python test suite does not
download model weights; hardware validation is a separate local run.

```powershell
Set-Location D:\space_esb_integration
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$env:CRATER_M2_SOURCE = (Get-Location).Path
& $py -m pytest -q
npm ci
npm test
npm run build
```

M2 serves canonical JSON over `ws://127.0.0.1:8765/telemetry` on loopback.
Copy `.env.example` to an ignored `.env.local`, set
`VITE_TELEMETRY_MODE=LIVE` and the WebSocket URL, then run `npm run dev`.
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
