# M1 → M2 offline ONNX integration

User requirements: import M1 commit `45cbf2f551bcf162709cd3dc0d8d6f4e86c1f35a`
without replacing M2/M3, launch actual `onnx-grounding-dino` on DirectML, accept
per-frame calibrated camera/pose, verify JSONL before continuous callbacks,
exercise blackout/buffering/retries/recovery and validate delivered WebSocket
frames with the actual M3 telemetry v1 parser. No cloud inference or synthetic
detector substitution. NASA camera poses are unavailable; calibrated demo is
being prepared by M1. Unknown poses must fail explicitly.

Architecture: retain M1 source byte-for-byte at the requested commit. M2 owns
backend dispatch and bounded callback handoff; each observation's camera is
projected independently onto the supplied ground plane in LOCAL_ENU_V1. The
existing binary CRC/ARQ/loss simulator feeds the existing loopback WebSocket.
No canonical M3 schema change is required. Runtime and model caches are explicit;
no weights download during inference. Use the current authorized M2 branch.

1. [ ] Synchronize only M1-owned source/tests/dependency files from the pinned
   commit; preserve M2, assistant, shared packaging and examples. Run full suite,
   verify source tree equality, commit and push independently.
2. [ ] Add failing launcher tests for ONNX/DirectML selection and invalid backend
   device combinations; implement local-only dispatch and relevant M1 settings.
   Expose M1 metrics and handoff statistics in M2 reports. Run full suite, commit,
   push and check CI.
3. [ ] Add independent known-coordinate tests for changing per-frame intrinsics,
   camera translation/rotation and rover pose; null/missing poses fail. Replay
   calibrated JSONL through binary loss/blackout/recovery; collect actual socket
   messages and validate every frame with pinned M3 parser. Synthetic fixtures
   test geometry/transport only and are labeled as such.
4. [ ] Run actual prepared ONNX model callback entirely offline when the M1 Python
   environment/cache and a calibrated video are available. Export model identity,
   provider, inference/callback/radio metrics, delivered counts and M3 validation.
   Without these prerequisites, complete unaffected work and record the precise
   remaining limitation; never invent NASA poses or report a fake ONNX success.
5. [ ] Independent review, final tests, atomic single-line Conventional Commits
   without bodies/trailers, push to `feat/spatial-telemetry`, verify CI.
