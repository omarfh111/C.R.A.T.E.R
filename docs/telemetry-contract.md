# Telemetry contract v1

Member 2 should deliver canonical JSON frames matching `src/telemetry/contract.ts` over a WebSocket. One WebSocket text message contains one JSON object. The browser validates each message before Mission Control state changes. Wire formats used by rover hardware can differ: translate them to this contract in a bridge outside the UI. No hardware-specific fields or protocol are assumed here.

```json
{
  "schemaVersion": 1,
  "roverId": "rover-1",
  "sequence": 42,
  "capturedAt": "2026-10-10T12:00:00.000Z",
  "roverPosition": { "frameId": "LOCAL_ENU_V1", "xM": 2.5, "yM": 1.2, "zM": 0 },
  "positionUncertaintyRadiusM": 0.3,
  "link": { "status": "connected", "packetsSent": 42, "packetsLost": 2 },
  "hazards": [{
    "id": "hazard-1",
    "type": "crater",
    "position": { "frameId": "LOCAL_ENU_V1", "xM": 3.1, "yM": 2, "zM": -0.2 },
    "confidence": 0.87,
    "uncertaintyRadiusM": 0.4,
    "observedAt": "2026-10-10T11:59:59.900Z"
  }]
}
```

## Semantics

- `schemaVersion` is exactly `1`. A breaking change requires a new version and parser.
- `roverId` identifies a stream. `sequence` is an increasing integer for **generated frames**, starting at any nonnegative value. Replayed packets keep their original sequence. Mission Control accepts only a sequence greater than the last accepted one per rover.
- `capturedAt` and `observedAt` are ISO 8601 timestamps with timezone offsets. They are rover clock times. `observedAt` must not be later than `capturedAt`. Mission Control adds `receivedAt` from its own clock when a packet arrives. Clock skew is allowed, so receipt time can precede capture time.
- `LOCAL_ENU_V1` is a local right-handed East-North-Up frame: x east, y north, z up, all in meters. Origin is the rover's agreed mission start marker. Member 2 must calibrate or translate measurements into this frame before emitting frames; do not send latitude/longitude or pixels in these fields.
- `positionUncertaintyRadiusM` and each hazard's `uncertaintyRadiusM` are nonnegative approximate spatial radius bounds in meters. `confidence` is a unit interval `[0, 1]` representing observation confidence, not a percentage.
- Hazard `id` is stable for the same physical hazard and `type` is `crater`, `rock`, `slope`, or `unknown`. `hazards` is the set observed in this frame; it may be empty. A hazard is not deleted merely because a later frame omits it.
- `link.status` is the rover's assessment when the frame was captured. `packetsSent` and `packetsLost` are cumulative nonnegative rover-reported counters, with lost no greater than sent. Mission Control separately counts received, rejected, duplicate, out-of-order, and sequence-gap packets. During a blackout no frame may arrive, so Mission Control's transport status can differ from the last reported rover link status.
- Unknown fields are rejected. Invalid JSON and schema failures are counted and never update accepted state.

## Live integration

Set `VITE_TELEMETRY_MODE=LIVE` and `VITE_TELEMETRY_WS_URL=ws://127.0.0.1:8765/telemetry` in `.env.local`, then restart Vite. The WebSocket endpoint is provided by Member 2 or a later bridge. A browser page served over HTTPS requires `wss://`. The app does not assume a hardware transport, packet framing, or backend implementation. See the adapter interface in `src/telemetry/adapter.ts` for the source boundary.
