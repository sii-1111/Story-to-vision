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
