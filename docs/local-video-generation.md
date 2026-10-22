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

## Decision for a 4 GiB NVIDIA GPU with about 12 GiB system RAM

This hardware profile is **experimental-only** for local video generation. Do not start by downloading a full-size LTX or Wan checkpoint: runtime overhead, model weights, activations, and frame buffers can exceed available memory. CPU offload may reduce VRAM demand but often makes rendering much slower and can still exhaust system RAM.

Recommended order:

1. Keep screenplay generation local and continue building/testing the creator workflow.
2. If a local video experiment is still desired, inspect the official CogVideoX-2B Diffusers documentation and exact checkpoint license first; investigate quantization and CPU offload. Do not assume the 2B label guarantees it fits.
3. Check free disk space and close GPU-heavy applications before any manual download. Do not download weights as part of app startup or CI.
4. Start with the smallest supported frame count and resolution, record peak VRAM/RAM and elapsed time, decode the resulting video, and stop if the process swaps heavily or runs out of memory.
5. If it cannot render reliably, keep video generation behind an explicit optional provider interface and develop against user-supplied sample clips. Hosted generation remains opt-in and must never be a silent fallback.

A hardware preflight cannot promise this machine will render any particular model. Confirm compatibility using the exact current model card and runtime docs before installing.
