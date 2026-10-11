# Story-to-Vision

An AI-powered story-to-video studio for turning written stories into structured episodic screenplays and, in later milestones, generated vertical video episodes.

## MVP direction

The first milestone establishes a tested FastAPI foundation for story submission and screenplay planning. The project will grow toward direct video generation through a replaceable provider adapter, persistent story/character continuity, asynchronous generation jobs, and 9:16 episode assembly.

## Current status

- [x] Repository initialized
- [ ] Story planning API and validated screenplay schema
- [ ] LLM-backed screenplay planning
- [ ] Video-provider integration and asynchronous jobs
- [ ] Episode assembly, quality checks, and export

## Development

The API lives in `apps/api`. See its README for local setup and test commands.

## Security

- Never commit `.env` files or API keys.
- Keep `.env.example` limited to placeholder values.
