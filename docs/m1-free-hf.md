# Free Hugging Face inference check (2026-10-10)

The best working free candidate found in this check is
`IDEA-Research/grounding-dino-base` through the public ZeroGPU Space
https://huggingface.co/spaces/developer0hye/Grounding_DINO_Base_demo .
This is a community demo API, separate from the paid Inference Providers
router. The existing HF_TOKEN successfully authenticated the test; no token
permission change, paid subscription or local model download was needed.
No account or billing settings were changed.

## Live comparison

| Candidate | Access test | Result |
| --- | --- | --- |
| Grounding DINO Base, public ZeroGPU Space | Succeeded with existing token | Pixel bounding boxes and detector scores returned on 3 NASA frames |
| Florence-2-base, gokaygokay/Florence-2 Space | Failed before inference | API metadata returned Internal Server Error on both attempts; model accuracy unknown |
| Qwen3-VL through HF Inference Providers | Previous request refused with HTTP 402 | Account has no remaining credits; switching router models does not supply credits |

Grounding DINO is suitable for experimenting with text-guided rock detection
because it provides boxes and detector scores directly. It does not perform
tracking or metric 3D localization. The hosted Space is using the Base model;
this check did not benchmark Tiny against Base.

Prompt: `rock. stone. boulder.`; box threshold 0.25; text threshold 0.2.
Use the left 1280x960 view of First AutoNav. Independent calls on frames 0,
10 and 20 took 10.12, 6.99 and 2.86 seconds respectively. These timings
include client setup where applicable, upload, queue, inference and result
retrieval. They are not pure GPU latency or a guaranteed frame rate.

The three-frame preliminary annotation scope includes individual rocks at
least 30x20 pixels. At IoU >=0.5, the result was 5 true positives, 1 false
positive and 3 false negatives: precision 83.3%, recall 62.5%. These are
pilot measurements on a tiny manually labeled sample, not validated accuracy
claims. Frame 0 missed both annotated targets. Frame 20 produced a box over
most of the terrain. The earlier prompt `a rock.` also produced a terrain
false positive. Detection quality needs improvement and broader evaluation
before relying on these observations for obstacle avoidance. No tracking
accuracy was measured.

## Cost, permissions and constraints

Official ZeroGPU documentation currently gives signed-in free accounts
5 minutes of GPU time per daily quota period. This is GPU time, not five
minutes of video or wall-clock processing. Quota resets 24 hours after first
GPU usage. Queue length, actual remaining quota and Space availability vary;
no remaining-quota value was obtained in this check. Free access is suitable
for sparse development tests, not an assured low-latency continuous feed.

The current token already works. Keep it in ignored `.env`; no broader write,
administrator or billing-management permission is needed for this tested
public-Space call. Public Space ownership and API availability can change.

Images are uploaded to the community Space. Remote inference conflicts with
the challenge's local perception requirement. This candidate is an
experimental development option; the existing compliant local implementation
remains available. The pipeline's `--backend hf-hosted` still targets the
paid router: this research did not silently switch that backend to Spaces.

Evidence: [saved comparison](validation/hf-free-spaces.json).
Local rendered results are under `outputs/space-comparison/` (ignored by Git).
The check used `gradio-client==1.13.3` with `huggingface-hub==0.36.2`; pip
reported no broken requirements. Existing tests: 40 passed, 3 skipped because
optional local-model/M2 integration resources were not enabled in this run.

Sources:
- https://huggingface.co/docs/hub/spaces-zerogpu
- https://huggingface.co/docs/inference-providers/pricing
- https://huggingface.co/spaces/developer0hye/Grounding_DINO_Base_demo/blob/main/app.py
- https://huggingface.co/spaces/gokaygokay/Florence-2/blob/main/app.py
