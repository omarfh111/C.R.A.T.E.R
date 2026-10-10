# M2 implementation plan

Goal: implement the agreed M3-compatible spatial/telemetry pipeline.
Spec: `docs/m2-design.md`. Execution: inline, as requested by the user.
Dependencies: Python >=3.11, NumPy >=1.26,<3, websockets >=15,<16; pytest >=8,<9.

## Review focus

- Invalid/horizon pixels must not become plausible map coordinates.
- Bad bytes, quantization boundaries and counter overflow must fail explicitly.
- Lost ACK must not duplicate station observations or reorder sequences.
- Blackouts and queue overflow must remain bounded and measurable.
- Slow/disconnected WS clients must not stall radio processing; timestamps must
  remain capture times and payloads must pass M3's exact parser.

## 1. Geometry and canonical JSON

- [x] Tests first: `tests/test_geometry.py`, `tests/test_contract.py`, observe RED.
- [x] Implement `crater_m2/geometry.py`, `crater_m2/contract.py` and package config.
- [x] Verify round trip on known ENU points, bad rays, rotation and strict JSON.
- [x] Run full suite; commit and push this verified increment.

## 2. Binary codec

- [ ] Tests first: `tests/test_codec.py`, observe RED.
- [ ] Implement `encode_frame(frame)->bytes`, `decode_frame(bytes)->dict` and ACK
  encoding/decoding in `crater_m2/codec.py`.
- [ ] Verify bounded quantization, CRC, Unicode IDs, malformed/truncated packets,
  enums and overflow. Run full suite; commit and push.

## 3. Reliable constrained transport

- [ ] Tests first: `tests/test_radio.py`, observe RED.
- [ ] Implement `LinkConfig`, `RadioLink`, `ReliableTransport` in
  `crater_m2/radio.py`: virtual monotonic clock, seeded loss, serialization in
  both directions, blackout intervals, FIFO stop-and-wait and station dedupe.
- [ ] Verify delay/bandwidth, ACK loss, full blackout recovery, bounded buffers
  and retry exhaustion. Run full suite; commit and push.

## 4. Source adapters, WebSocket bridge and reproducible demo

- [ ] Tests first: `tests/test_source.py`, `tests/test_bridge.py`, observe RED.
- [ ] Implement calibrated scenario and JSONL M1 adapter in `crater_m2/source.py`.
- [ ] Implement `TelemetryBridge` in `crater_m2/bridge.py`, loopback bind, exact
  path and bounded per-client output queues. Clients see decoded deliveries only.
- [ ] Implement CLI `python -m crater_m2`: configurable link/source, report file,
  finite benchmark or live demo; graceful shutdown and queue drain timeout.
- [ ] Add M2-specific docs, example M1 file, GitHub Actions Python workflow.
- [ ] Run suite, benchmark and actual websocket reception; validate the generated
  JSON fixture against the Zod contract on M3's branch. Review, commit and push.

## Progress

Initial: design reconciled with M3 contract; main has no application baseline.
User explicitly requested immediate execution; no further design gate imposed.
Task 1: RED missing package, then GREEN 31/31 tests on Python 3.12. Verified
known ENU projections, strict schema and invalid geometry. Existing local Python
has required dependencies; no model/download or environment installation needed.
