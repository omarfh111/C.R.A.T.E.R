# Read-only assistant HTTP contract

This is the implemented optional Mission Intelligence science sidecar, independent of canonical M2 → M3 WebSocket v1. It accepts reference questions, returns local evidence and unverified explanations, and exposes no rover controls, telemetry mutations, journal endpoints, image processing, or HTTP-selected filesystem/report paths.

Use the [Windows launcher and measured runtime guide](mission-intelligence.md) for the supported 4096-context / 240-output / top-three / 120-second keep-alive / 45-second deadline configuration. The default two-command Quick Demo does not start or depend on this service.

## Transport and origin configuration

The server binds `127.0.0.1`, default port 8766. Requests require exactly one trusted `Host`, either `127.0.0.1:<service port>` or `localhost:<service port>`. Duplicate Host/Origin headers, unexpected origins, and spoofed host suffixes are rejected. A native local request may omit Origin; loopback is not local-process authentication.

Browser origins must be exact HTTP loopback origins with an explicit canonical port, for example `http://127.0.0.1:50554`. There is no trailing slash, path, query, fragment, username, or wildcard. Allowed origin hosts are `127.0.0.1`, `localhost`, and `[::1]`; the sidecar itself is IPv4-bound. `localhost` and `127.0.0.1` origins are distinct.

The optional launcher supplies the exact dynamic dashboard origin:

```powershell
.\scripts\start-assistant.ps1 -DashboardOrigin 'http://127.0.0.1:50554'
```

For direct CLI use, `serve --allow-origin <origin>` can be repeated. Providing it **replaces** the fixed development defaults, which otherwise permit localhost/127.0.0.1 at ports 5173 and 4173 only. Do not broaden CORS to accommodate dynamic ports; pass the actual origin printed by the dashboard launcher.

Trusted browser responses echo that one origin in `Access-Control-Allow-Origin`, with `Vary: Origin`, allowed methods `GET, POST, OPTIONS`, and allowed header `Content-Type`. Credentials are not used. OPTIONS performs preflight without model work. The server emits JSON UTF-8, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, and a restrictive response Content-Security-Policy. Browser and backend clients reject redirects and use explicit loopback URLs; no remote Ollama host is accepted by the hardened adapter.

## GET /health

```json
{
  "status": "ready",
  "httpReady": true,
  "modelStatus": "available",
  "busy": false,
  "inferenceState": "idle",
  "indexedChunks": 24,
  "llm": "qwen3:4b-instruct-2507-q4_K_M",
  "embedding": "embeddinggemma:300m"
}
```

`httpReady` means the HTTP service and loaded index are ready. `modelStatus` is cached metadata/prerequisite state: `unchecked`, `available`, or `unavailable`. It is not a fresh model load, generation, GPU-offload test, or guarantee the next question will succeed. Health does not wait for inference or contact Ollama. The supported launcher separately performs startup generation and checks Qwen GPU residency before announcing readiness.

`inferenceState` is:

| Value | Meaning |
| --- | --- |
| `idle` | No inference is admitted. |
| `running` | One question owns the inference slot. |
| `capture_blocked` | The enabled process guard detects live M1/M2 capture, or cannot establish its absence. |
| `timeout_requires_restart` | A prior aggregate inference timeout quarantined this sidecar. |

`busy` is true for running, capture-blocked, and quarantined states. Priority between blocked states is an implementation detail; any non-idle state should prevent another question. Model unavailability still permits HTTP 200 health responses. A disconnected service is a transport failure, not an `httpReady` response.

## POST /ask

```json
{"question":"How do NASA stereo navigation cameras help assess terrain?","topK":3}
```

Only `question` and optional `topK` are accepted. `question` must contain non-whitespace text and be at most 2000 characters. `topK` must be an integer from 1 to 8; the API default is 4 and the dashboard sends 3. Booleans, unknown keys, missing/empty questions, and malformed JSON are invalid.

A request requires `Content-Type: application/json`, exactly one valid Content-Length, and a body from 1 to 16,384 bytes. Chunked/Transfer-Encoding bodies and ambiguous lengths are refused. Body reads have a five-second socket timeout. Requests do not select report filenames, source paths, model names, URLs, or context budgets.

### Successful answer

The following is an abbreviated shape; source text and digest must be actual returned evidence, not placeholders in a real response:

```json
{
  "status": "answered",
  "answer": "A short explanation grounded in the excerpt [S1].",
  "sources": [{
    "sourceId": "S1",
    "path": "local/source.md",
    "lineStart": 1,
    "lineEnd": 7,
    "digest": "<64 lowercase hexadecimal characters>",
    "score": 0.75,
    "text": "Actual indexed excerpt",
    "sourceUrl": "https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/",
    "verifiedOn": "2026-10-10"
  }],
  "citedSourceIds": ["S1"],
  "facts": null,
  "models": {
    "embedding": "embeddinggemma:300m",
    "llm": "qwen3:4b-instruct-2507-q4_K_M"
  },
  "roles": ["retriever", "report_analyst", "explainer", "citation_identity_validator"],
  "verification": "unverified_generated",
  "limitations": "Generated explanations are unverified; citation checks do not establish semantic truth."
}
```

`path` is a local display/provenance label, potentially absolute; it is not a browser-fetch endpoint. `lineStart` and `lineEnd` identify the source chunk. `digest` is the source file SHA-256, not a signature or scientific certification. `score` is retrieval similarity, not factual confidence. External summary chunks carry `sourceUrl` and `verifiedOn`; internal contracts need not. `verifiedOn` means source consultation date, not publication date or guarantee that the remote page is unchanged.

Source IDs are unique within a response, from `S1` through `S9`. At most eight retrieved passages are returned; an explicitly operator-configured fixed M2 report may add one deterministic facts passage. Sources may include retrieved passages not cited by the answer. Every inline citation must appear in `citedSourceIds`, every declared citation must appear inline, and each must identify an actual returned source. An answered result requires at least one citation. IDs are response-local; do not reuse them across questions.

An optional report is chosen by the CLI operator when starting the server, never by an HTTP client. Its `facts` object is computed from validated M2 report fields before generation. The normal dashboard launcher selects no report, so `facts` is null. Generated prose is never copied into `facts`, accepted telemetry, or hazard state. Role labels describe code stages and do not assert independent semantic reviewers.

### Insufficient evidence

HTTP 200 also returns `status: "insufficient_evidence"`. The operator receives a bounded explanation of the limitation, no claimed verified measurement, and `verification: "not_generated"`. Sources may still describe retrieved context, but `citedSourceIds` is empty for a plain abstention.

Recognized requests for current operational measurements return `reason: "operational_facts_require_telemetry"` before retrieval/model calls and direct the operator to the deterministic inspector. Unsupported numeric assertions can return `reason: "unsupported_numeric_claim"`. The model can also return an explicit abstention without a reason field.

These are conservative guards, not semantic truth verification. Citation identity, numeric presence in cited text, and source-cache consistency do not prove that a generated sentence is entailed. Passing generated answers remain `unverified_generated` and require human interpretation. A reference about a NASA or ESA mission does not validate C.R.A.T.E.R.'s measured performance.

## Errors, deadlines, and capacity

Errors use bounded JSON without echoing question text, private excerpts, or document contents:

```json
{"code":"busy","error":"An assistant request is already running; retry after it completes"}
```

| HTTP | `code` | Meaning / operator action |
| --- | --- | --- |
| 400 | `invalid_request` | Invalid request schema, body, encoding, or headers. Correct the request. |
| 403 | `forbidden` | Untrusted Host or Origin. Use the actual configured dashboard origin. |
| 404 | `not_found` | Unknown endpoint. |
| 429 | `busy` | Inference already admitted, live capture blocked, timeout quarantine, or HTTP connection capacity reached. |
| 500 | `failed` | Unexpected sidecar failure. Inspect local service state. |
| 502 | `invalid_response` | Invalid/truncated model output, mismatched citations, altered evidence/index, or other response validation failure. |
| 503 | `unavailable` | Ollama or required local model unavailable. HTTP can remain healthy. |
| 504 | `timeout` | Aggregate question deadline expired; model termination is not guaranteed. Restart safely as described below. |

The sidecar has eight bounded HTTP workers and an eight-connection listen backlog by default. It admits exactly **one inference** and has **no question queue**. Ordinary busy responses include `Retry-After: 2`. Extreme connection-capacity shedding happens before trusted headers are parsed, so that minimal 429 response has no CORS echo; a browser may show a transport/unavailable error instead. The bounded behavior remains intentional.

The supported launcher sets the backend question budget to 45 seconds across model metadata checks, retrieval embedding, and generation calls. It is an aggregate monotonic deadline, not 45 seconds independently for every operation. Local source reconstruction and response delivery add bounded work around model transport. Startup is separately budgeted at 180 seconds per CLI call; it is not an ordinary HTTP question.

On timeout, the sidecar enters `timeout_requires_restart` and refuses subsequent inference with 429. This prevents overlap with a backend generation whose termination is uncertain. Health remains responsive and reports the quarantine. Stop the owned launcher (which stops its own isolated Ollama and runners), inspect the logs, and restart it after confirming live capture is inactive. With `-UseExistingOllama`, the operator must manage that selected runtime; the launcher does not terminate its server.

Browser cancellation uses AbortController and prevents stale UI completions. It does not promise cancellation of Ollama computation. A disconnected HTTP client leaves the inference slot occupied until backend completion or deadline. There is no automatic retry of generated questions and no silent fallback to cloud inference.

## TypeScript and dashboard behavior

`integrations/m3-assistant-client.ts` exports typed `health()` and `ask(question, topK, signal)` operations. It validates loopback service URLs, bounded streamed responses, source metadata, citation correspondence, and health fields. Requests use `credentials: 'omit'`, `redirect: 'error'`, and `cache: 'no-store'`. The default client question timeout is 120 seconds, while health is bounded to at most five seconds; the supported sidecar normally returns its own 45-second timeout first. Changing the browser timeout is not a backend execution policy.

Client error states are `unavailable`, `busy`, `timeout`, `invalid_response`, `failed`, `cancelled`, and `invalid_request`. `insufficient_evidence` is a valid answer state, not a network error. The React panel keeps question state independent of WebSocket reception and deterministic mission facts. It starts no model work until the operator explicitly connects and asks.

## Validation scope

The [real-model runtime record](validation/mission-intelligence/runtime.json) exercised readiness, grounded NASA/ESA responses, operational abstention with zero model requests, false-premise/injection abstention, concurrent busy handling, responsive health, client disconnection, unavailable Ollama, and timeout quarantine. Its structural gates all passed; the artifact explicitly does not certify semantic truth or browser rendering.

Offline Python/client tests cover altered cached excerpts and metadata, mismatched citation IDs, unsupported measurements, malformed/truncated responses, redirects, host/origin restrictions, bounded concurrency, and error states. The [Mission Intelligence guide](mission-intelligence.md) records measured performance, actual browser validation, coexistence limits, and deferred experience functionality. Model-free CI never requires Ollama or a GPU.
