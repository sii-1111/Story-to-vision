# Free local video-generation evaluation

This milestone prepares a hardware-aware evaluation of open-weight video generation. It intentionally does not select a final model until the target machine is measured and a short real clip is benchmarked.

## 1. Offline hardware preflight

From the repository root, run:

```powershell
python scripts/local_video_hardware_check.py
```

The script reports system memory, detected NVIDIA GPU model/VRAM/driver, and a rough candidate tier. It does not download model weights, install dependencies, call hosted inference, or submit jobs. Treat its recommendation as a starting point, not a compatibility guarantee.

## 2. Candidate model families

| Candidate | Why evaluate it | Important constraints to verify |
| --- | --- | --- |
| LTX-Video / current LTX family | Good first candidate for short, relatively fast local video experiments; supports text-to-video and image-conditioned workflows in supported releases | Exact checkpoint, VRAM at target resolution/frame count, license for the chosen checkpoint, runtime/ComfyUI version, output quality |
| Wan 2.1 / later Wan releases | Useful quality baseline; text-to-video and image-to-video variants, with different model sizes | Large variants can require substantial VRAM; verify the exact model card, quantization, supported resolution, and license |
| CogVideoX family | Another open-weight comparison point with established community/runtime integrations | Hardware demand varies by checkpoint; verify license, maintenance status, and reproducible local inference path |

Model names and releases change. Before installing anything, check the official model card and license for the exact checkpoint and the runtime's current documentation. “Open weights” does not automatically mean unrestricted commercial use, and a free download does not remove local compute/electricity costs.

## 3. Fair benchmark plan

Use the same short prompt, seed where supported, resolution, frame count, and output codec for each candidate. Start with a low-resolution, short clip and increase settings only after it succeeds.

Record:
- exact checkpoint/revision, license, runtime and GPU driver
- resolution, frame count, FPS and clip duration
- cold-start time, generation wall-clock time, peak VRAM/RAM, and errors
- decoded output, black/frozen-frame checks, visual prompt adherence, motion quality and anatomy artifacts
- character consistency across at least three scenes using the same reference image when image-conditioning is supported

A successful API response is not a successful video. Decode the resulting file and inspect representative frames; keep a human review step for identity drift. Compare actual elapsed time and memory rather than relying on model-family marketing.

## 4. Integration and cost guardrails

- Local generation remains the default path.
- Do not submit a Replicate/hosted video job unless the creator explicitly enables and confirms that provider.
- Never silently fall back from local generation to a hosted provider.
- Make model weights/checkpoints an explicit user-managed download; do not pull multi-gigabyte files during app startup or CI.
- Keep provider adapters replaceable so the existing optional Replicate integration remains available without becoming mandatory.

## 5. What this milestone does not claim

The hardware preflight is not a model benchmark and does not install or generate a clip. The final model choice remains pending until the user's actual hardware and a reproducible local render test are known.
