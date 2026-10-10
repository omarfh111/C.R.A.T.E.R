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

## Integration M1 (continuation authorized by user)

Inspected and merged `feat/ai-perception` at
`9d3eebc` into the M2 branch, preserving both Python packages, entry points,
optional AI/hosted dependencies and ignored artifacts. Shared package metadata
resolved rather than overwriting either member. CI now executes M1/M2 interface
tests against the code in this checkout. Local result: 118 passed, 1 skipped
(explicit opt-in offline learned-model smoke; weights not installed for this run).
M1's calibrated JSONL already matches M2, and its per-observation callback allows
live integration without waiting for file completion. Uncalibrated NASA/remote
perception must never acquire invented metric coordinates. Next bounded change:
connect that callback through a bounded handoff to the existing M2 radio/WS loop,
with finite source, error propagation, shutdown and real client tests.

Live integration: added `--perception-video` (local Grounding DINO or controlled
contrast backend), calibration required, bounded callback handoff and one worker.
RED tests for missing stream, late producer errors, input/output collisions,
capture-time snapshots and live deadline boundary; guards and historic DATA
snapshots corrected them. Duration includes model startup explicitly; a mission
with zero observations is incomplete rather than successful. Worker shutdown is
cooperative and waits for ongoing inference; residual observations are counted.
Read-only review findings addressed; detailed histories remain finite-mission
scope. Local full suite: 129 passed, 1 opt-in learned-model smoke skipped.
Actual local CLI controlled-video run: 30 observations offered/consumed/delivered/
ACKed, 20 retransmissions, 7 station-suppressed radio duplicates, no discarded
observations, finish 21.51 wall seconds. Radio 4096 bytes/s, latency 0.1 s,
jitter 0.05 s, loss probability 20%, blackout 1-2 s, seed 7, drain allowance 60 s.
Initial 6 s drain run correctly reported 19 delivered and 11 pending (incomplete).
Final 30 JSONs accepted by M3's actual parser. Its contract is unchanged on the
newer `feat/mission-control` head. See `docs/validation/m1-m2-live.json`.
Merge increment `917d7d1` CI succeeded before the live increment was published.

## Independent M2 continuation while M1 evolves

User requested a new branch check and useful independent work while M1 is in
progress. M1 head `a0c660e` adds free remote Space experiments; compared the four
new commits to the integrated `9d3eebc`. Camera/observation contracts and local
pipeline callback are unchanged. Do not modify or merge its evolving remote
backends into this increment; keep the verified local boundary.

Replace growing M2 metric lists with streaming count/mean/max and exact byte
totals. Cap rejected details (default100) while preserving total counts. Cap
radio snapshot history (default4096) with a cumulative baseline; old capture
queries fail explicitly, preserving correct capture-time semantics. Tests first:
long metric stream, overflow-safe mean, bounded history, equality at eviction
boundary, invalid/old timestamps and 200 rejections with only3 stored details.
All limits exposed in CLI/report; no M3 canonical schema change.
Independent review checked history against uncapped references at capacities1..5,
including repeated timestamps and eviction equality. Fixed a partial-report byte
average regression (RED then GREEN): a failed mixed-rover enqueue no longer adds
bytes without adding a generated frame. Full suite139 passed,1 optional AI smoke
skipped. Default benchmark unchanged:30/30 delivered,8709 radio bytes,58.14 s
virtual finish; all30 decoded JSONs accepted by M3. M1 head a0c660e CI is green;
its latest changes remain experimental remote modes outside this M2 increment.
