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

- [x] Tests first: `tests/test_codec.py`, observe RED.
- [x] Implement `encode_frame(frame)->bytes`, `decode_frame(bytes)->dict` and ACK
  encoding/decoding in `crater_m2/codec.py`.
- [x] Verify bounded quantization, CRC, Unicode IDs, malformed/truncated packets,
  enums and overflow. Run full suite; commit and push.

## 3. Reliable constrained transport

- [x] Tests first: `tests/test_radio.py`, observe RED.
- [x] Implement `LinkConfig`, `RadioLink`, `ReliableTransport` in
  `crater_m2/radio.py`: virtual monotonic clock, seeded loss, serialization in
  both directions, blackout intervals, FIFO stop-and-wait and station dedupe.
- [x] Verify delay/bandwidth, ACK loss, full blackout recovery, bounded buffers
  and retry exhaustion. Run full suite; commit and push.

## 4. Source adapters, WebSocket bridge and reproducible demo

- [x] Tests first: `tests/test_source.py`, `tests/test_bridge.py`, observe RED.
- [x] Implement calibrated scenario and JSONL M1 adapter in `crater_m2/source.py`.
- [x] Implement `TelemetryBridge` in `crater_m2/bridge.py`, loopback bind, exact
  path and bounded per-client output queues. Clients see decoded deliveries only.
- [x] Implement CLI `python -m crater_m2`: configurable link/source, report file,
  finite benchmark or live demo; graceful shutdown and queue drain timeout.
- [x] Add M2-specific docs, example M1 file, GitHub Actions Python workflow.
- [x] Run suite, benchmark and actual websocket reception; validate the generated
  JSON fixture against the Zod contract on M3's branch. Review, commit and push.

## Progress

Initial: design reconciled with M3 contract; main has no application baseline.
User explicitly requested immediate execution; no further design gate imposed.
Task 1: RED missing package, then GREEN 31/31 tests on Python 3.12. Verified
known ENU projections, strict schema and invalid geometry. Existing local Python
has required dependencies; no model/download or environment installation needed.
Task 2: RED missing codec; added extreme finite-number regression (RED overflow),
then explicit range guards before scaling. GREEN 46/46, including all truncations,
CRC corruption, representability and uncertainty rounding.
Task 3: RED missing transport, GREEN 60/60. Seeded 45% packet loss recovered
10/10 ordered observations; lost ACK generated radio duplicates removed before
station publication. Verified shared byte budget, blackout buffering, retry
exhaustion, capture preservation and adaptive timeout at 10 bytes/s.
Task 4: RED missing source/bridge, then GREEN 73/73 including real WebSocket
reception across blackout, CLI report and reconnect. Independent read-only review
found no Critical/Important issues. Added regression tests for nonfinite rays and
invalid timezone offsets (RED), corrected guards, GREEN 77/77. Metric histories
grow with mission duration; documented finite-mission scope rather than claiming
all runtime state is bounded. Defaults reduced from 2 to 1 FPS and drain extended
to 60 s after the 256 bytes/s experiment demonstrated queue overload at 2 FPS.
Default 30 s benchmark: 30/30 delivered/ACKed, 163 bytes/frame, 8709 total radio
bytes, 58.14 s virtual finish, maximum decoded localization error 0.0232 m.
All 30 messages accepted by M3's actual pinned Zod parser; M3's 16 tests and
production build passed in an ignored temporary checkout. Python wheel built.
Windows sandbox denies asyncio's local sockets and pip metadata renaming;
reruns with authorized elevated execution passed. No application workaround
or skipped network test introduced.
Remote publication verified: `c4e42964ebd9f4c36a935e004d4ca2a7ec46e95b` on
`origin/feat/spatial-telemetry`. GitHub Actions run 38077999204 failed before any
runner or step started: GitHub annotation says recent account payments failed
or the spending limit must be increased. Remote Python 3.11/3.12 execution is
therefore unverified; local Python 3.12, packaging, benchmark and M3 parser
checks passed. Account billing must be resolved by the owner, then CI rerun.
The documented M1 JSONL example additionally delivered/ACKed 3/3 observations;
all three decoded messages were accepted by M3's actual parser.
