# C.R.A.T.E.R. binary protocol v1

All integer fields use network byte order (big endian). Each DATA packet is
independent: no hidden ID lookup table or delta state is needed after a blackout.

## DATA header: 42 bytes (`>2sBIQiiiIBIIH`)

| Field | Bytes | Encoding |
|---|---:|---|
| magic | 2 | ASCII CR |
| version | 1 | 1 |
| sequence | 4 | uint32, generated sequence, unchanged on retry |
| capturedAt | 8 | uint64 UTC milliseconds since Unix epoch |
| rover x/y/z | 12 | 3 x int32, millimetres in LOCAL_ENU_V1 |
| rover uncertainty | 4 | uint32 millimetres, rounded upward |
| link status | 1 | 0 connected, 1 degraded, 2 disconnected |
| DATA packets sent / lost | 8 | 2 x uint32, cumulative at capture |
| hazard count | 2 | uint16 |

After header: rover ID (one-byte UTF-8 byte length followed by 1..255 bytes).
Then each hazard has its ID in the same format followed by 27 bytes (`>BiiiIHQ`):

| Field | Bytes | Encoding |
|---|---:|---|
| type | 1 | 0 crater, 1 rock, 2 slope, 3 unknown |
| x/y/z | 12 | 3 x int32 millimetres |
| uncertainty | 4 | uint32 millimetres, rounded upward |
| confidence | 2 | uint16: round(confidence * 65535) |
| observedAt | 8 | UTC milliseconds |

The final 4 bytes are CRC32 over all preceding bytes. Maximum total packet length
65507 bytes. Out-of-range data are rejected, never silently wrapped or clipped.
Coordinates have at most 0.5 mm quantization error per axis; confidence error is
at most 1/(2*65535). Sub-millisecond timestamp precision is truncated; timezone
offsets are normalized to UTC. Uncertainty rounding is always upward.

For rover-1 and the three scenario hazards: 163 bytes per DATA frame.

## ACK: 11 bytes

`>2sBI` : ASCII CA, version 1, sequence uint32, followed by CRC32 uint32.
ACK packets use the same byte-limited lossy medium as DATA. The sender waits for
ACK before sending the next queued frame. A lost ACK can trigger repeated DATA;
the station acknowledges repeated DATA but publishes the observation only once.

## Scope

The simulator has one rover stream per transport instance. Its received callback
is the station-side boundary; the JSON bridge publishes only after decoding.
The radio script counts its DATA/ACK packet bytes, not physical modulation or
operating-system network headers. The WebSocket is a separate local station link.
