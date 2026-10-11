# Seven-minute live demonstration

For a fresh clone, begin with the [Start Here launchers](../README.md#start-here). The paths and timed commands below preserve the original DirectML rehearsal; the Quick Demo launcher replays its recorded ONNX observations with an explicit **RECORDED ONNX REPLAY** label.

This presentation uses two **actual** Grounding DINO Tiny ONNX + DirectML passes over the same hash-checked 30-frame calibrated video. The first pass populates Mission Control. The second pass keeps its station WebSocket connected while a simulated rover radio blackout holds new pixel-derived observations, then retransmits them. In a separate fallback, M2 can replay previously recorded genuine ONNX observations. Neither path uses simulator boxes as detections. See the [Windows integration guide](end-to-end-integration.md) for environment setup.

## Prepare before the audience arrives

1. Use the validated DirectML environment and cached pinned FP32 model. Confirm the source video hash is `74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9`:

   ```powershell
   (Get-FileHash 'D:\space_esb_m1\outputs\m1-final-scene\scene.mp4' -Algorithm SHA256).Hash.ToLowerInvariant()
   ```

2. From `D:\space_esb_integration`, run `npm ci` if needed. Put `VITE_TELEMETRY_MODE=LIVE` and `VITE_TELEMETRY_WS_URL=ws://127.0.0.1:8765/telemetry` in ignored `.env.local`. Start `npm run dev` in terminal A. Open `http://127.0.0.1:5173/` in a **fresh** browser telemetry session and let the intro finish.
3. Keep terminal B ready with the commands below. Port 8765 must be free. Run B in the **same browser session** after A; its `--start-sequence 30` continues after A's 0–29. Close diagnostic WebSocket receivers before the audience run: `--wait-for-client` starts capture when *any* client connects, and late browser subscribers cannot recover earlier WebSocket frames. If either phase delivers fewer than 30 frames, check the report and compare the browser's accepted count with `received-jsonl`. Use a fresh browser and a valid increasing sequence for a retry. Do not weaken sequence checks or rewrite capture timestamps.

```powershell
Set-Location D:\space_esb_integration
$py = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$env:CRATER_M2_SOURCE = (Get-Location).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
$common = @('--perception-video','D:\space_esb_m1\outputs\m1-final-scene\scene.mp4', '--calibration','D:\space_esb_m1\outputs\m1-final-scene\calibration.json', '--perception-backend','onnx-grounding-dino', '--device','directml', '--cache-dir','D:\space_esb_m1\.cache\huggingface', '--perception-buffer','4', '--no-preview', '--duration','45', '--drain','60', '--fps','10', '--bandwidth','4096', '--latency','.005', '--jitter','0', '--loss','.25', '--queue','128', '--attempts','20', '--seed','7', '--port','8765', '--wait-for-client','15')
```

Phase A — live inference, normal radio. Start at 0:00:

```powershell
& $py -m crater_m2 @common --no-blackout --start-sequence 0 --perception-output "outputs\demo-$tag-a-perception" --report "outputs\demo-$tag-a-report.json" --received-jsonl "outputs\demo-$tag-a-frames.jsonl"
```

Phase B — **another live inference pass**, simulated 5–40 second radio blackout. Start after A exits and its report confirms 30 delivered and acknowledged, around 0:35 in the measured presentation. If startup is slower, shift the following segments and shorten the later explanations:

```powershell
& $py -m crater_m2 @common --blackout 5:40 --start-sequence 30 --perception-output "outputs\demo-$tag-b-perception" --report "outputs\demo-$tag-b-report.json" --received-jsonl "outputs\demo-$tag-b-frames.jsonl"
```

The blackout clock starts when M2's mission starts, **after** the browser connects, and includes model startup. Warm-cache startup during the measured rehearsal was short enough for the 5–40 second interval to overlap inference and block transport until recovery. Watch the CLI and dashboard rather than assuming startup always takes the same time. If model startup consumes the interval, stop claiming a live blackout overlap and use the replay fallback below. During radio blackout the station WebSocket stays connected; the map keeps the last accepted telemetry and its capture age rises. Between A and B, the station itself briefly disconnects because the first process has exited; identify this separately. Phase B may deliver all held frames in a burst after radio recovery, still showing their original capture timestamps as aged/stale.

| Presentation time | Operator action | Expected screen and explanation |
| --- | --- | --- |
| 0:00–0:35 | Show the hash and start phase A. | Actual local ONNX inference begins; point to the reported DirectML/CPU provider list. |
| 0:35–1:20 | Point out A's three persistent rock IDs, then start B and show its rover radio blackout. | M1 processing FPS differs from M2's `--fps 10`; the station WebSocket remains connected while capture age rises. The scene is synthetic and calibrated. |
| 1:20–2:05 | Show higher accepted sequences and recovery. Compare `capturedAt`, received time and a hazard with B's received JSONL. | M2 retransmits CRC-checked binary packets with ACKs; M3 rejects invalid, duplicate and old sequences. |
| 2:05–3:00 | Compare A/B JSON reports with the browser counters captured in each frame. | Read final generated/delivered/acknowledged/lost/retransmission totals from the reports; dashboard packet counters reflect the last accepted capture, so they can lag or show zero during blackout. The 4,096 bytes/s radio and 25% loss are simulated. The binary frame averaged 177 bytes in rehearsal. |
| 3:00–4:15 | Inspect the last accepted spatial map, three IDs, confidence, uncertainty and capture age. The short-lived station may now show TRANSPORT DOWN. | Coordinates derive from ONNX boxes and known synthetic camera pose. Confidence is not a calibrated probability. |
| 4:15–5:15 | Explain the source-video hash, evidence bundle and distinction between live inference and recorded predictions. | The replay is genuine previous ONNX output, with historical capture timestamps. |
| 5:15–6:15 | Reload a fresh LIVE browser session and run the **recorded ONNX replay** fallback below. | The five-second simulated startup blackout lets the WebSocket settle. Confirm 30 accepted frames; call this replay, never live AI. |
| 6:15–7:00 | State measured controlled-scene errors and limits. | The 0.097 m mean localization error is synthetic-scene evidence only. Uncalibrated NASA clips cannot supply metric rock positions. |

## Rehearsal evidence and operating checks

On 2026-10-11 local time, with the RTX 5070 laptop and the exact video hash above, phase A finished in 17.65 s: 30/30 generated, delivered and acknowledged; 3 rock tracks; M1 processing 3.77 FPS. Phase B finished in 50.26 s: 30/30 generated, delivered and acknowledged; M1 processing 3.44 FPS; perception buffer high-water mark 1 of 4; 28 DATA retransmissions, 17 DATA and 11 ACK packets lost. The second capture ran from 23:42:02.338Z through 23:42:10.815Z; the first B frame arrived at 23:42:34.939Z and the last at 23:42:43.913Z. All 60 frames reached the same browser session in increasing sequence 0–59. During B's blackout the browser displayed `STALE` with station transport connected and retained the rock inventory; after recovery it accepted the newer frames. Mean B radio delivery latency was 31.90 s. This is one measured run with seed 7, not a guarantee on another machine. Ignored local reports and actual WebSocket arrivals are under `outputs/release-rehearsal-20261011/`.

The **complete timed operator rehearsal** on the same host began at 01:15:00 and ended at 01:22:11 local time (7 min 11 s wall time). A began at 0:00 and finished at 0:19; B began at 0:34 and finished at 1:25; the explicitly labeled recorded replay began at 5:22 and finished at 5:40. A/B each yielded 30/30 delivered and acknowledged, 90 pixel-derived detections and three stable IDs, with processing at 3.60/3.67 FPS respectively. Mission Control accepted live seq 0–59 without gaps, showed `STALE` while B's WebSocket remained connected during radio blackout, then accepted recovery. The fresh browser accepted all 30 replayed frames at seq 0–29, with historical capture age and no console errors. Each live phase recorded 28 retransmissions, 17 DATA losses and 11 ACK losses; the replay used the same 25% loss with a separate five-second startup blackout. The controlled-scene re-evaluation remained 90 TP, 0 FP, 0 FN, mean IoU 0.814 and 0 ID switches. Reports and browser screenshots are ignored local evidence under `outputs/release-rehearsal-pass-20261011/`. For a strict 7:00 slot, trim the closing explanation by 11 s.

The operator should pause or expand the explanations to fit seven minutes; the two 30-frame missions themselves finish in about a minute each. Check that the station is connected before each capture; check report `completed`, `source.producerCompleted`, `source.interrupted`, `transport.delivered`, `transport.acknowledged`, `transport.pending` and `transport.abandoned` before calling the mission successful. If the station disconnects **during** a radio blackout, diagnose the WebSocket connection; do not describe it as radio loss.

## GPU or timing fallback: genuine recorded ONNX replay

If model startup, DirectML inference or presentation timing fails, say aloud: **“This is a replay of previously recorded local ONNX detections, not live AI inference.”** Close any diagnostic WebSocket receiver, confirm port 8765 is free, and reload Mission Control so its packet accounting reads `RECEIVED 0`. Keep the browser open and awaiting the station. From terminal B, in the same environment, run M2's real transport and WebSocket bridge using the committed observations. The first five seconds are an explicit **simulated startup radio blackout**: packets queue while the browser WebSocket settles, then the real transport releases them. The fresh browser permits `--start-sequence 0`; if retaining an existing browser session, choose a sequence above its last accepted frame:

```powershell
& $py -m crater_m2 --input examples\m1-onnx-calibrated\observations.jsonl --input-ground-z 0 --duration 15 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout 0:5 --queue 128 --attempts 20 --seed 7 --port 8765 --wait-for-client 15 --start-sequence 0 --report "outputs\demo-$tag-replay-report.json" --received-jsonl "outputs\demo-$tag-replay-frames.jsonl"
```

Verify both the M2 report (`delivered` and `acknowledged` 30/30) **and** Mission Control (`ACCEPTED 30`, final seq 29 in a fresh session). `SEQ GAPS 0` alone is insufficient because a browser can miss frames *before its first accepted sequence*. The station report also does not prove that a late WebSocket subscriber received all frames. Two timed trials exposed this: an auxiliary logger connected first and the browser accepted only 10/30; in a fresh browser without that logger, the short `.5:2` blackout still let the first two frames arrive before M3 connected, yielding 28/30. The explicit `0:5` startup blackout then produced 30/30 accepted in a fresh browser with zero sequence gaps, using the same 25% loss and real M2 transport. If any frame is missing, disclose it and retry with a fresh session; do not call that presentation pass complete. Historical `capturedAt` values remain historical, so Mission Control shows the replay as aged/stale. This fallback validates transport and dashboard integration using genuine prior ONNX results but does not satisfy the live hardware gate. Keep the [validation report](integration-validation.md) and local reports available for detailed questions.
