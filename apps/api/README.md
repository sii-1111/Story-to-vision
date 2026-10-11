# Story-to-Vision API

FastAPI service for validating story input and generating a structured short-episode screenplay through an OpenAI-compatible chat-completions endpoint.

## Requirements

- Python 3.11+
- An API key and model name for a compatible LLM provider to generate screenplays

## Run locally (PowerShell)

From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` and set `LLM_API_KEY` and `LLM_MODEL`. `LLM_BASE_URL` defaults to the OpenAI API base URL; change it to your provider's compatible endpoint if needed. Never commit the real `.env` file.

Start the API from the repository root so the root `.env` file is discovered:

```powershell
uvicorn app.main:app --app-dir apps/api --reload
```

Open http://127.0.0.1:8000/docs for interactive API docs.

## Tests

From the repository root:

```powershell
pip install -e ".[dev]"
$env:PYTHONPATH = "apps/api"
pytest apps/api/tests -q
ruff check apps/api
```

The health check and request validation work without credentials. Story planning returns HTTP 503 until a provider key and model are configured; provider failures or invalid screenplay output return a safe HTTP 502 message.

## Endpoint

`POST /api/stories/plan`

Example request:

```json
{
  "title": "The Last Promise",
  "story": "Mira returns to her hometown after five years and discovers a letter that could change her relationship with her childhood friend.",
  "genre": "romance",
  "visual_style": "cinematic realism",
  "language": "English",
  "episode_duration_seconds": 45
}
```

The response contains a validated screenplay with 4–6 scenes, stable character IDs, visual directions, dialogue, continuity notes, and a cliffhanger. Generated scene durations are checked against the requested episode length.

## Direct scene video generation

The video adapter submits a selected screenplay scene to Replicate and exposes the provider's asynchronous job status. Configure these variables in the backend-only root `.env` file:

- `VIDEO_API_TOKEN`: Replicate API token.
- `VIDEO_MODEL`: selected Replicate model in `owner/model` format.
- `VIDEO_API_BASE_URL`: defaults to `https://api.replicate.com/v1`.
- `VIDEO_PROMPT_FIELD`, `VIDEO_ASPECT_RATIO_FIELD`, `VIDEO_DURATION_FIELD`: model-specific input field names. Set the aspect-ratio or duration field to an empty value if the selected model does not accept that input.

**Important:** Replicate models do not share one universal input schema. Review the selected model's input schema and set these field names accordingly; some models may need additional inputs or different value types, which should be added to the adapter before use. The initial adapter sends a text prompt, a 9:16 aspect ratio, and a duration capped at 10 seconds. Provider/model usage is paid according to the provider's pricing; no free generation is assumed.

Endpoints:

- `POST /api/videos/jobs` — request a clip for a scene in a validated screenplay.
- `GET /api/videos/jobs/{job_id}` — retrieve provider status and, on success, the output video URL.

Example request body for `POST /api/videos/jobs`:

```json
{
  "screenplay": { "...": "a complete Screenplay object from /api/stories/plan" },
  "scene_number": 1
}
```

Jobs are tracked by the provider; the app does not persist a local job database in this milestone. Use the status endpoint to refresh queued/processing jobs. Generated output URLs are provider-hosted and may expire; download/export persistence and full-episode assembly are future work. Video provider tokens stay on the server and must never be exposed through frontend variables.

## Assemble and download a complete episode

Generate a clip for each screenplay scene and refresh each job until its status is `succeeded`. Then submit the full screenplay and one provider job ID per scene, in screenplay order:

```http
POST /api/episodes/assemble
Content-Type: application/json
```

The response includes an `episode_id` and a `download_url`. Download the MP4 from that URL. The API downloads provider output only from HTTPS `replicate.delivery` hosts, limits each source clip to 250 MB, and uses FFmpeg to normalize clips to 1080×1920 at 30 fps. Dialogue is burned in as subtitles; original generated audio is not retained in this initial assembly pass.

Set `EPISODE_EXPORT_DIR` to choose the output directory. Docker Compose uses a persistent named volume at `/app/data/exports`. Install FFmpeg with subtitle support for non-Docker local runs. Exports are local to the API instance; configure backups and access controls before production use. This milestone does not yet provide authentication, multi-user isolation, automated clip-quality checks, or cloud object storage.


## Persistent projects and character universe

The API stores projects, screenplay JSON, character profiles, and generation-job status in SQLite. Configure `DATABASE_PATH` (default `data/story_to_vision.sqlite3`). The web app uses:

- `POST /api/projects` — create a project or update its latest saved screenplay.
- `GET /api/projects` — list saved projects and episode/character counts.
- `GET /api/projects/{project_id}` — restore a project, latest screenplays, character profiles, and tracked video jobs.

Save a project before starting scene video generation to associate provider jobs with that project. Refreshing a tracked job updates its saved status. Docker Compose mounts a named `story_data` volume at `/app/data`, keeping SQLite data and episode exports across container recreation. This milestone does not include authentication, concurrent multi-user isolation, schema migrations, or remote object storage; do not expose this API publicly without adding those controls.


## Episode technical quality checks

After assembling an MP4, request `GET /api/episodes/exports/{episode_id}/quality-check`. The endpoint inspects the video with FFprobe and decodes the full video stream with FFmpeg. It reports dimensions, codec, duration, frame-rate metadata, file size, and individual checks for vertical 1080×1920 output, H.264, usable duration, and full decode. FFmpeg and FFprobe are installed in the API Docker image. It also runs FFmpeg black-frame detection for segments over 2 seconds and freeze detection for segments over 3 seconds. Intentional fades and still shots can trigger these checks, so treat them as review signals. The report does not evaluate character consistency, composition, dialogue timing, or audio quality.


## Character continuity audit

POST `/api/stories/continuity-check` with `{ "screenplay": ... }` to receive a text-based continuity report, stable visual anchors extracted from each character's canonical appearance, per-scene matched traits, and recommendations. The score measures whether screenplay action or visual direction repeats appearance terms; it is not a probability of visual identity match. The video prompt builder injects the full canonical character appearance into each scene prompt. For pixel-level review, use `POST /api/stories/visual-identity-check` with canonical character reference images and representative generated-frame images. Configure `VISUAL_IDENTITY_MODEL` to a vision-capable model supported by the same OpenAI-compatible endpoint and set `LLM_API_KEY`. The request accepts base64 JPEG, PNG, or WebP images (4 MiB maximum each; up to 8 references and 24 frames). Images are sent to the configured provider for analysis and are not persisted by this endpoint. The model returns a subjective 0–100 resemblance estimate, visible matches, differences, and a `consistent`, `drift_detected`, or `uncertain` verdict. These scores are not calibrated probabilities or biometric identity verification; human review remains required. The Creator Studio Cast tab includes upload controls for reference portraits and generated frames.
