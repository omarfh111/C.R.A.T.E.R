# C.R.A.T.E.R. Mission Control

A local React + TypeScript + Vite + Tailwind telemetry foundation for ATEC'26. It runs with deterministic mock rover traffic by default. A real source can replace the mock through one WebSocket adapter. There is no application backend or cloud dependency: the browser needs only a canonical JSON WebSocket endpoint when using live telemetry.

## Start on Windows

Prerequisite: Node.js 20.19+ or 22.12+ and npm. Node 24 was used for validation.

```powershell
cd D:\space_esb
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. The default `MOCK` mode needs no server or `.env` file. Run `npm test` for focused telemetry tests and `npm run build` for a TypeScript checked production build. `npm run preview` serves the built app locally.

## Lunar mission intro

On launch, a five-second cinematic approach crosses a procedural lunar surface toward a crater and rover. **Skip Intro** is available immediately. **Replay Intro** is in the dashboard header. The dashboard stays mounted while the intro plays, so telemetry continues to arrive; replay never resets telemetry state. The overlay dissolves into the existing functional dashboard.

The scene uses locally installed Three.js, procedural terrain, stars, lighting and a rover model. Fonts and the still-image fallback are bundled locally; there are no CDN requests. If WebGL 2 cannot start, the intro displays the local lunar image and hands off after a shorter sequence. `prefers-reduced-motion: reduce` uses the still image, avoids WebGL, and hands off quickly. The intro renderer, animation loop and resize observer are released when the overlay closes.

The provided `Sentinel Autonomous Orbital Intelligence.zip` remains untouched in the project root. It and `.sentinel-reference/` are ignored by Git. The new scene adapts the reference's timed reveal, camera movement, starfield, lighting and restrained typography to a lunar surface setting; no Earth imagery or orbital mechanics are included. Phase 2 dashboard redesign is outside this implementation.

For local overrides, copy `.env.example` to `.env.local`, edit the values, and restart Vite. `.env.local` is ignored by Git. In `LIVE` mode set `VITE_TELEMETRY_WS_URL` to a WebSocket endpoint emitting the canonical v1 JSON frame as one text message per frame. The UI shows a configuration error when the URL is absent. The endpoint and any bridge from rover hardware are supplied by Member 2. For a page served over HTTPS, use `wss://`.

## Architecture

```text
MOCK schedule ─┐
               ├─> TelemetryAdapter events ─> strict v1 validation ─> ordering/duplicate reducer ─> React state
LIVE WebSocket ┘
```

- `src/telemetry/contract.ts`: versioned Zod runtime schema and inferred TypeScript types.
- `src/telemetry/mock.ts`: deterministic rover frame generation and delivery schedule. `generated` contains every rover frame; `deliveries` contains only packets reaching Mission Control after configured delay, drops, duplication, reordering, and blackout.
- `src/telemetry/adapter.ts`: common source interface. Mock and live produce the same packet and transport status events. The live source forwards raw JSON; validation happens in the common reducer.
- `src/telemetry/state.ts`: receipt counts, schema rejection, per-rover sequence ordering, and accepted state. Mission Control receipt time is separate from rover capture time.
- `src/main.tsx`: functional dashboard for latest position, hazards, mode, connection, and packet counts. The broader Phase 2 dashboard redesign is intentionally absent.
- `src/intro/lunarScene.ts`: procedural WebGL lunar scene, camera choreography, renderer sizing and cleanup.
- `src/intro/LunarIntro.tsx`: timing, Skip, reduced-motion and fallback handoff.

The mock starts at the browser's current time, then uses deterministic ticks. Given the same `startMs` and config, the generated frames and delivery schedule are identical. Set `VITE_MOCK_SEED` for a different deterministic path. Zero for `LOSS_EVERY`, `DUPLICATE_EVERY`, or `REORDER_EVERY` disables that effect. The default blackout begins at tick 20 and lasts five ticks; the transport status changes to disconnected and returns to connected. A silent live WebSocket is marked stale after five seconds without an accepted frame. The mock ends after `TOTAL_TICKS` and marks the transport disconnected.

## Member 2 integration

The exact schema, example frame, units, coordinate frame, timestamp and counter meanings are in [docs/telemetry-contract.md](docs/telemetry-contract.md). The stable boundary is canonical JSON over WebSocket. A hardware packet decoder may run in Member 2's process or a later local bridge; it must map to the v1 fields before sending. No assumptions about hardware framing or transport are embedded in Mission Control.

Use stable rover and hazard IDs, increasing frame sequences, timezone-qualified ISO timestamps, and meters in `LOCAL_ENU_V1` with the agreed mission start marker as origin. Keep rover-reported packet counters in the frame; Mission Control maintains its own receipt and rejection counts. The reducer accepts only newer sequences per rover, so delayed older packets cannot move the displayed rover backward. Sequence gaps are an inference from accepted frames, not a definitive lost-packet count. If the contract needs a breaking change, negotiate v2 instead of changing v1 silently.
