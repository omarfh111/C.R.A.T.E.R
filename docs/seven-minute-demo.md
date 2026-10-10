# Seven-minute live demonstration

Use the [Windows integration guide](end-to-end-integration.md) for prerequisites and exact commands. Before the audience arrives, verify the scene SHA-256, model cache and `.env.local`, run `npm ci`, start `npm run dev`, and open a fresh browser at `http://127.0.0.1:5173`. Keep the terminal with M2's command prepared. Use an empty, ignored `outputs/demo-perception-new` path. Confirm the M2 port 8765 is free. Historical capture timestamps are never changed.

| Time | Operator action | What to show and say |
| --- | --- | --- |
| 0:00–0:45 | Show the local video hash and cached ONNX revision; start the M2 continuous DirectML command from the guide. | The model is local Grounding DINO Tiny ONNX, not cloud inference. DirectML may fall back to CPU for some operators. |
| 0:45–1:45 | Let the real model load; show the terminal provider and processing report as frames arrive. | Detections come from video pixels. Report measured processing FPS separately from configured replay FPS. |
| 1:45–2:45 | Switch to Mission Control LIVE after the intro. Point to three tracked hazards, confidence, uncertainty circles, rover coordinates and `LOCAL_ENU_V1`. | These are calibrated synthetic scene positions derived from detected boxes. |
| 2:45–3:30 | Show M2 binary/radio counters and final report when available. | 177-byte binary frame average in the validated run; bytes include CRC, retries and ACKs. |
| 3:30–4:45 | Use the configured 9:15 s blackout while capture is active; show rover link status and STALE age. | Radio interruption and station WebSocket connection are distinct. The last accepted map stays visible. If model startup shifts the interval, explain timing and use replay fallback. |
| 4:45–5:45 | Show recovered higher sequences, rover movement and unchanged rock IDs. Compare a displayed value with `outputs/demo-frames-new.jsonl`. | M3 accepts newer validated frames; it rejects duplicates and older sequences. |
| 5:45–6:30 | Show loss/retransmission/ACK/delivery totals from M2's JSON report. | In the validated seed-7 run all 30 frames were delivered despite 25% configured loss; this is not guaranteed for every scenario. |
| 6:30–7:00 | State the controlled-scene spatial error and limitations. | The 0.097 m mean error is on a known synthetic scene and does not establish real lunar mapping. The NASA clips have no matching calibration. |

### Honest fallback when live GPU loading fails

Use the **previously recorded genuine ONNX observations** from `examples/m1-onnx-calibrated/observations.jsonl`. State aloud that this is replay, not live inference. Start M2 with `--input examples/m1-onnx-calibrated/observations.jsonl --input-ground-z 0 --duration 10 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:2 --queue 128 --attempts 20 --seed 7`, plus a fresh `--report` and `--received-jsonl` path. Use a fresh browser telemetry session or an increasing `--start-sequence`. Historical timestamps will correctly show aged/stale; do not rewrite them. The fallback demonstrates transport and dashboard integration from real recorded model output but does **not** pass the live hardware gate.

Keep `outputs/onnx-live-final/validation.json`, `outputs/browser-blackout-m2-report.json` and browser screenshots available to answer detailed questions. They are local ignored evidence, not committed assets. The tracked bundle and [validation report](integration-validation.md) contain the shareable evidence and limitations.
