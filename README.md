# Story-to-Vision

An AI-powered story-to-video studio for turning written stories into structured episodic screenplays and submitting individual scenes for provider-generated vertical video clips.

## MVP direction

The first milestone establishes a tested FastAPI foundation for story submission and screenplay planning. The project will grow toward direct video generation through a replaceable provider adapter, persistent story/character continuity, asynchronous generation jobs, and 9:16 episode assembly.

## Current status

- [x] Repository initialized
- [x] Story planning API and validated screenplay schema
- [x] Configurable OpenAI-compatible LLM screenplay planner
- [ ] Connect and verify a chosen LLM provider with real credentials
- [x] Replicate video-provider adapter and asynchronous job status API
- [ ] Persistent job/story storage and durable output downloads
- [ ] Persistent story and character continuity
- [x] Episode assembly and MP4 export
- [ ] Automated visual quality checks
- [x] Creator-friendly web interface with scene refinement and video clip controls

## Development

The API lives in `apps/api`. See [the API README](apps/api/README.md) for local setup, configuration, and tests.

## Security

- Never commit `.env` files or API keys.
- Keep `.env.example` limited to placeholder values.
- LLM and video providers are configured server-side; no real provider credentials are included.
- Replicate model input fields vary; configure the chosen model schema before generating clips.
