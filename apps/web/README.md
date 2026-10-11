# Story-to-Vision Creator Studio

The first web UI milestone: a responsive story editor, genre and visual-direction controls, episode settings, and a screenplay/cast preview connected to the FastAPI planner.

## Requirements

- Node.js 20+
- The FastAPI backend from `apps/api`
- An LLM provider configured for the backend to generate a real screenplay

## Run locally

Terminal 1 — API (from the repository root):

```bash
python -m pip install -e .
uvicorn app.main:app --app-dir apps/api --reload
```

Terminal 2 — web app:

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000. The Next.js rewrite proxies `/api/stories/*` to the FastAPI server at `http://127.0.0.1:8000` by default.

To point the web app at another API host, set `STORY_API_URL` in the environment before starting Next.js. Restart the dev server after changing it.

## Important

- The UI does not fabricate screenplay results. If the backend or LLM provider is unavailable, it displays the API error.
- Configure LLM credentials only on the backend; never use a `NEXT_PUBLIC_*` variable for secrets.
- Video generation and MP4 export are not implemented in this milestone.
