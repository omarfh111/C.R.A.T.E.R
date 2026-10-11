# Mission Intelligence measurement evidence

Validation date: 2026-10-11. Branch: `feat/m2-assistant-integration`.
Pinned M2 source: `57b29439ced649fc5ca9bb39918beef2aa387c83`.

These are durable copies of actual local measurements, not example results.
All measured numbers, model digests, generated answers, returned evidence,
failures and limitations are retained. The copies are byte-for-byte identical
to the originals; `manifest.json` records both original and bundle SHA-256.

| Durable file | Original local artifact |
| --- | --- |
| [nvidia-benchmark.json](nvidia-benchmark.json) | `outputs/mission-intelligence-nvidia-01.json` |
| [runtime.json](runtime.json) | `outputs/mission-intelligence-runtime-03.json` |
| [coexistence.json](coexistence.json) | `artifacts/assistant-coexistence-02/coexistence.json` |

## Sanitization and completeness

The path policy replaces absolute integration-worktree, M1-worktree and user
profile prefixes with `<worktree>`, `<m1-worktree>` and `<user-home>`, respectively.
An unclassified absolute local path requires review rather than silent copying.
None of the three JSON originals contained absolute local paths, so no path
replacement was necessary. Relative corpus paths, official NASA/ESA/arXiv URLs
and relevant loopback endpoints remain intact.

No fields or arrays were omitted. These summary artifacts contain no large raw
resource-sample arrays; recorded sample counts and resource maxima are retained.
Every JSON string was checked for private-key markers, common GitHub/OpenAI/AWS/
Google API-key patterns and credentials in HTTP URLs. No matches were found.
This bounded pattern scan is not a comprehensive secret-detection guarantee.
The source artifacts were read only and remain untouched.

## Timing interpretation

The legacy benchmark's case, `indexBuild` and `retrieval` `elapsedS` values include
resource-monitor shutdown/cleanup. They must not be presented as isolated answer
latency. Individual `calls[].elapsedS` values for `/api/chat` and `/api/embed`
remain valid measured HTTP-call latencies. Ollama load, prompt-evaluation and
generation durations are retained in their original nanoseconds; token counts
and throughput retain their original values. The runtime harness separately
measured complete HTTP response latency in `response.elapsedS`.

Resource peaks are sampled device/system measurements, not allocator maxima.
Coexistence compares repeated real DirectML captures under unloaded, loaded-idle
and active-generation conditions. The recorded active-generation degradation
supports preventing concurrent science generation during live capture. No
failure, truncated response or structural-versus-semantic limitation has been
removed to improve the reported result.

The files describe one Windows machine and prepared questions. Citation identity
checks do not certify semantic truth, and external research does not validate
this rover's measured performance. These copies do not claim a browser
cancellation pass or a fresh Quick Demo result; those checks are documented
separately. See [manifest.json](manifest.json) for hashes and preservation counts.


Additional derived validation artifacts are listed separately in the manifest:
[quick-demo.json](quick-demo.json), [gpu-runtime.json](gpu-runtime.json),
[launcher-guard.json](launcher-guard.json), and the actual
[browser screenshot](mission-intelligence.jpg). These are reports/excerpts or
a screenshot, not byte-identical copies of the three original measurement
JSONs above. Their provenance and SHA-256 values are recorded individually.
The final browser cancellation and fresh-demo checks are documented in
[the browser record](../mission-intelligence-browser.md).
