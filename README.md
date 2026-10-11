# Story-to-Vision

An AI-powered story-to-video studio for turning written stories into structured episodic screenplays and, in later milestones, generated vertical video episodes.

## MVP direction

The first milestone establishes a tested FastAPI foundation for story submission and screenplay planning. The project will grow toward direct video generation through a replaceable provider adapter, persistent story/character continuity, asynchronous generation jobs, and 9:16 episode assembly.

## Current status

- [x] Repository initialized
- [x] Story planning API and validated screenplay schema
- [x] Configurable OpenAI-compatible LLM screenplay planner
- [ ] Connect and verify a chosen LLM provider with real credentials
- [ ] Video-provider integration and asynchronous jobs
- [ ] Persistent story and character continuity
- [ ] Episode assembly, quality checks, and export
- [ ] Creator-friendly web interface

## Development

The API lives in `apps/api`. See [the API README](apps/api/README.md) for local setup, configuration, and tests.

## Security

- Never commit `.env` files or API keys.
- Keep `.env.example` limited to placeholder values.
- The LLM provider is configurable; no real provider credentials are included.
