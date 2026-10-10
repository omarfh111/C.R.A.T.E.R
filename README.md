# C.R.A.T.E.R. Mission Control

A local React + TypeScript + Vite + Tailwind Mission Control for ATEC'26. It runs with deterministic mock rover traffic by default. A real source can replace the mock through one WebSocket adapter. There is no application backend or cloud dependency: the browser needs only a canonical JSON WebSocket endpoint when using live telemetry.

## Start on Windows

Prerequisite: Node.js 20.19+ or 22.12+ and npm. Node 24 was used for validation.

```powershell
cd D:\space_esb
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. The default `MOCK` mode needs no server or `.env` file. Run `npm test` for the telemetry, intro and dashboard tests, and `npm run build` for a TypeScript checked production build. `npm run preview` serves the built app locally.

## Lunar mission intro

In a fresh browser tab, a five-second cinematic approach crosses a procedural lunar surface toward a crater and rover. The intro marks itself started in `sessionStorage` as soon as playback begins, so a reload in the same tab opens Mission Control immediately, even if the reload happens during playback. A separate fresh tab plays the intro again. **Replay Intro** is in the dashboard header and does not change this refresh behavior. There are no controls inside the intro. The dashboard stays mounted while the intro plays, so telemetry continues to arrive; replay never resets telemetry state. A synchronized 900 ms crossfade darkens the lunar scene and brings the dashboard upward into view before the intro unmounts. If browser storage is unavailable, the app still runs and the intro plays on each load.

The scene uses locally installed Three.js, procedural terrain, stars, lighting and a rover model. Fonts and the still-image fallback are bundled locally; there are no CDN requests. If WebGL 2 cannot start, the intro displays the local lunar image and hands off after a shorter sequence. `prefers-reduced-motion: reduce` uses the still image, avoids WebGL, and hands off quickly. The intro renderer, animation loop and resize observer are released when the overlay closes.

The provided `Sentinel Autonomous Orbital Intelligence.zip` and `Mission Control preview status.zip` remain untouched in the project root and are ignored by Git. The lunar scene adapts the former reference's timed reveal, camera movement, starfield, lighting and restrained typography; no Earth imagery or orbital mechanics are included. The Claude Design dashboard is integrated as production React code; the reference prototype is not shipped.

For local overrides, copy `.env.example` to `.env.local`, edit the values, and restart Vite. `.env.local` is ignored by Git. In `LIVE` mode set `VITE_TELEMETRY_WS_URL` to a WebSocket endpoint emitting the canonical v1 JSON frame as one text message per frame. Member 2's intended local endpoint is `ws://127.0.0.1:8765/telemetry`. The UI shows a configuration error when the URL is absent. The endpoint and any bridge from rover hardware are supplied by Member 2. For a page served over HTTPS, use `wss://`.

## Mission Control dashboard

The tactical map places the rover, trail and hazard markers at coordinates from **accepted** v1 frames in `LOCAL_ENU_V1` meters. Its procedural terrain is illustrative, not surveyed lunar imagery. Dashed trail segments mark inferred sequence gaps; uncertainty discs use reported radii. Click a marker or inventory row to inspect a hazard, drag or scroll the map to pan and zoom, or use its layer, fit and follow controls. The rover, communications, packet, inspector and event panels all derive from accepted telemetry and the Mission Control receipt journal.

The source chip always displays `MOCK` or `LIVE`. The `DEMO` menu exists only in `MOCK` mode; its presets restart the local mock adapter and clear that mock session's counters. Replay Intro does not restart telemetry. The dashboard adapts to desktop, tablet and mobile widths and bundles all map, font and intro assets for offline use.

Mission Control separates three signals: the station WebSocket transport status, the age of the last accepted frame, and the rover link status last reported **at the frame's capture time**. A connected but silent LIVE socket becomes `STALE` after five seconds; this does not confirm a radio blackout. A closed LIVE socket becomes `TRANSPORT DOWN`, with current rover radio status unknown. Only the labeled MOCK schedule reports a simulated radio blackout. Sequence gaps are inferred from accepted frames and are not a definitive lost-packet count. The current LIVE adapter opens one WebSocket; restart the page after a dropped connection unless the endpoint itself reconnects upstream.

## Architecture

```text
MOCK schedule ─┐
               ├─> TelemetryAdapter events ─> strict v1 validation ─> ordering/duplicate reducer ─> accepted state
LIVE WebSocket ┘                                                                      └─> receipt journal ─> dashboard/map
```

- `src/telemetry/contract.ts`: versioned Zod runtime schema and inferred TypeScript types.
- `src/telemetry/mock.ts`: deterministic rover frame generation and delivery schedule. `generated` contains every rover frame; `deliveries` contains only packets reaching Mission Control after configured delay, drops, duplication, reordering, and blackout.
- `src/telemetry/adapter.ts`: common source interface. Mock and live produce the same packet and transport status events. The live source forwards raw JSON; validation happens in the common reducer.
- `src/telemetry/state.ts`: receipt counts, schema rejection, per-rover sequence ordering, and accepted state. Mission Control receipt time is separate from rover capture time.
- `src/main.tsx`: source configuration, intro handoff and mounted Mission Control.
- `src/mission-control/hooks/useMissionTelemetry.ts`: shared adapter/reducer integration; the canonical validator and reducer remain in `src/telemetry/`.
- `src/mission-control/model/`: accepted-frame journal, communications derivation and pure display selectors.
- `src/mission-control/components/`, `map/` and `mission-control.css`: modular dashboard and procedural Canvas 2D tactical map.
- `src/intro/lunarScene.ts`: procedural WebGL lunar scene, camera choreography, renderer sizing and cleanup.
- `src/intro/LunarIntro.tsx`: timing, reduced-motion and fallback handoff.
- `src/intro/useIntroPlayback.ts`: tab-scoped playback marker, replay and handoff state.

The mock starts at the browser's current time, then uses deterministic ticks. Given the same `startMs` and config, the generated frames and delivery schedule are identical. Set `VITE_MOCK_SEED` for a different deterministic path. Zero for `LOSS_EVERY`, `DUPLICATE_EVERY`, or `REORDER_EVERY` disables that effect. The default simulated blackout begins at tick 20 and lasts five ticks; the mock transport status changes to disconnected and returns to connected. The mock ends after `TOTAL_TICKS` and marks the transport disconnected.

## Member 2 integration

The exact schema, example frame, units, coordinate frame, timestamp and counter meanings are in [docs/telemetry-contract.md](docs/telemetry-contract.md). The stable boundary is canonical JSON over WebSocket. A hardware packet decoder may run in Member 2's process or a later local bridge; it must map to the v1 fields before sending. No assumptions about hardware framing or transport are embedded in Mission Control.

Use stable rover and hazard IDs, increasing frame sequences, timezone-qualified ISO timestamps, and meters in `LOCAL_ENU_V1` with the agreed mission start marker as origin. Keep rover-reported packet counters in the frame; Mission Control maintains its own receipt and rejection counts. The reducer accepts only newer sequences per rover, so delayed older packets cannot move the displayed rover backward. Sequence gaps are an inference from accepted frames, not a definitive lost-packet count. If the contract needs a breaking change, negotiate v2 instead of changing v1 silently.
