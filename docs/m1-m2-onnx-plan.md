# M1 → M2 offline ONNX integration

User requirements: import final M1 commit `94bcf577e0aa5e8f9310d3fadc62757b26ce657b`
without replacing M2/M3, launch actual `onnx-grounding-dino` on DirectML, accept
per-frame calibrated camera/pose, verify JSONL before continuous callbacks,
exercise blackout/buffering/retries/recovery and validate delivered WebSocket
frames with the actual M3 telemetry v1 parser. No cloud inference or synthetic
detector substitution. NASA camera poses are unavailable; calibrated demo is
being prepared by M1. Unknown poses must fail explicitly.

Update: M1 published its calibrated ONNX validation report at `94bcf57`,
against an older M2 commit (`8b1b95e`). The actual video, poses and ONNX
observations remain on its developer's PC. The latest M2 loss/blackout/live
WebSocket validation on that PC is still required.

Architecture: retain M1 source byte-for-byte at the requested commit. M2 owns
backend dispatch and bounded callback handoff; each observation's camera is
projected independently onto the supplied ground plane in LOCAL_ENU_V1. The
existing binary CRC/ARQ/loss simulator feeds the existing loopback WebSocket.
No canonical M3 schema change is required. Runtime and model caches are explicit;
no weights download during inference. Use the current authorized M2 branch.

1. [x] Synchronize only M1-owned source/tests/dependency files from the pinned
   commit; preserve M2, assistant, shared packaging and examples. Run full suite,
   verify source tree equality, commit and push independently.
2. [x] Add failing launcher tests for ONNX/DirectML selection and invalid backend
   device combinations; implement local-only dispatch and relevant M1 settings.
   Expose M1 metrics and handoff statistics in M2 reports. Run full suite, commit,
   push and check CI.
3. [x] Add independent known-coordinate tests for changing per-frame intrinsics,
   camera translation/rotation and rover pose; null/missing poses fail. Replay
   calibrated JSONL through binary loss/blackout/recovery; collect actual socket
   messages and validate every frame with pinned M3 parser. Synthetic fixtures
   test geometry/transport only and are labeled as such.
4. [ ] Run actual prepared ONNX model callback entirely offline when the M1 Python
   environment/cache and a calibrated video are available. Export model identity,
   provider, inference/callback/radio metrics, delivered counts and M3 validation.
   Without these prerequisites, complete unaffected work and record the precise
   remaining limitation; never invent NASA poses or report a fake ONNX success.
   User clarified that the prepared runtime/GPU/cache belong to the M1 developer's
   other PC. No ONNX weights are to be downloaded on Omar's PC. Reproducible
   commands are ready in m1-m2-onnx-integration.md; the actual GPU run is deferred
   to that PC once M1 supplies its validated calibrated sequence/cache path.
5. [x] Independent review, final tests, atomic single-line Conventional Commits
   without bodies/trailers, push to `feat/spatial-telemetry`, verify CI.
