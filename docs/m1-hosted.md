# Hugging Face hosted perception (experimental)

## Selected candidate

`Qwen/Qwen3-VL-30B-A3B-Instruct`, provider `deepinfra`, through the official
Hugging Face router. Qwen3-VL supports visual grounding. Public model metadata
lists DeepInfra as live when checked on 2026-10-10. Grounding DINO Tiny,
Florence-2-base and OWLv2 have no provider mapping at this check. DETR's
standard COCO labels do not include rocks, so it is not selected just because
it has an object-detection API. The 30B/A3B Instruct model avoids a separate
reasoning mode and is available from multiple providers. No assertion of best
NASA accuracy or lowest latency is made before a real image API test.

Cloud inference sends compressed camera frames to HF/DeepInfra. It violates
the challenge's local, no-external-cloud-API perception requirement. Use this
mode for development/experiments and label it honestly in the demo. Hosted
model scores are self-reported VLM certainty, not calibrated detector scores.
No metric depth/coordinates are inferred from a VLM answer. M2 still owns
calibrated localization.

## Minimal installation

```powershell
python -m venv .venv-hf
.\.venv-hf\Scripts\python -m pip install -r requirements-m1-hosted.txt
```

No torch, transformers, model download or GPU is needed. The existing project
`.venv` is also usable and already has the required lightweight packages.

## Token setup

Create a token at https://huggingface.co/settings/tokens with type
**Fine-grained**. Under **Inference**, enable **Make calls to Inference Providers**.
For this public model through the router, repository write/read permissions,
gated-model access, endpoint management, and organization scopes are not
required. Do not use an administrator/write token. HF account inference
credits/billing are separate from token permissions; a valid token does not
guarantee credits or provider availability.

Edit `.env` at the repository root and set `HF_TOKEN=hf_...`. Keep the token
out of chat, commits and command-line arguments. `.env` and `.env.*` are ignored;
only the empty `.env.example` is committed. Existing environment variables
take precedence over `.env`. The token is never printed by preflight or metrics.

```powershell
.\.venv\Scripts\python -m crater_m1 hf-check
.\.venv\Scripts\python -m crater_m1 run ..\vid3.mp4 --backend hf-hosted --view left --max-frames 1 --output outputs/hf-smoke
```

`hf-check` validates configuration without an authenticated API call.
The one-frame smoke test checks provider access, JSON grounding, preview and
measured latency. A run with no `--max-frames` is capped at three requests.
`HF_MAX_REQUESTS` is an additional session cap (default 100). No retries are
performed: interrupted requests may already have been charged. No silent
fallback to a local model or fake detections is performed.

To analyse the complete NASA clip after the smoke test:

```powershell
.\.venv\Scripts\python -m crater_m1 run ..\vid3.mp4 --backend hf-hosted --view left --max-frames 43 --output outputs/hf-nasa
.\.venv\Scripts\python -m crater_m1 evaluate outputs/hf-nasa/observations.jsonl examples/nasa-pilot-annotations.json --output outputs/hf-nasa/accuracy.json
```

## Validation and limitations

Automated tests use a fake HTTP transport to verify JPEG upload, original-image
pixel coordinates from normalized boxes, malformed JSON, truncated generation,
authentication/payment/rate-limit errors, timeouts, request budget, tracking,
JSONL provenance and preview encoding. These tests validate integration, not
model accuracy or live provider access. The real API test waits for HF_TOKEN.

Remote latency includes upload, provider queue and generation. Processing FPS
includes this delay and local tracking; provider-managed weights cannot be
pinned to a Hub revision. A failed API call stops the run rather than treating
an unknown frame as an obstacle-free image. Partial JSONL is retained for
inspection; a completed metrics report exists only for successful runs.

Sources:
- https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct
- https://huggingface.co/docs/inference-providers/index
- https://huggingface.co/docs/hub/security-tokens
- https://huggingface.co/docs/inference-providers/providers/deepinfra

## Live smoke test status (2026-10-10)

Token configuration passed. The real NASA one-image request was refused by
Hugging Face with HTTP 402: no remaining credits; prepaid credits or PRO
monthly credits are required. No model output was obtained, so neither
accuracy nor remote inference latency is validated. Add credits at
https://huggingface.co/settings/billing and repeat the one-frame smoke command
with a new output directory. Changing token permissions does not resolve a
credit balance refusal. Free accounts currently have no included inference
credits according to the official pricing documentation:
https://huggingface.co/docs/inference-providers/pricing
