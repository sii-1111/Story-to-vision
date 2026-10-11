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
