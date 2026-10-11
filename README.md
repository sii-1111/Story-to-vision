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
- [x] SQLite-backed story projects, saved screenplays, character profiles, and generation-job history
- [ ] Durable cloud output downloads
- [x] Persistent story and character continuity
- [x] Episode assembly and MP4 export
- [x] Automated technical quality checks for exported videos
- [x] Creator-friendly web interface with scene refinement and video clip controls

## Persistent creator projects

Save a project from Creator Studio to store the original story, latest screenplay, stable character profiles, and provider generation-job history. Use **My episodes** to reopen saved projects. SQLite data and MP4 exports share the Docker Compose `story_data` volume. This MVP is intended for a single trusted creator; authentication, multi-user access controls, database migrations, and cloud object storage remain future work.

## Character continuity bible

Open the **Cast** tab and choose **Audit continuity** to review each character's canonical appearance, reusable visual anchors, and scenes where the screenplay should repeat recognizable traits. The report provides a text-based coverage score and scene-level suggestions before video generation. The existing video prompt builder also injects each character's canonical appearance into every scene prompt. This audit is not face recognition and cannot confirm that generated video pixels preserve identity; human review or a future visual-embedding comparison is still required.

## Episode technical quality gate

After assembling an MP4, choose **Run quality check** in Creator Studio. The API uses FFprobe to inspect resolution, codec, duration, and stream metadata, then decodes the full video with FFmpeg to catch technical corruption. The report lists each pass/fail result and basic file metadata. It also scans for prolonged black segments (over 2 seconds) and potentially frozen segments (over 3 seconds). These are review signals rather than proof of a bad shot: intentional fades or still shots may need creator review. This is not a computer-vision assessment of character identity, composition, audio, or narrative quality.

## Development

The API lives in `apps/api`. See [the API README](apps/api/README.md) for local setup, configuration, and tests.

## Security

- Never commit `.env` files or API keys.
- Keep `.env.example` limited to placeholder values.
- LLM and video providers are configured server-side; no real provider credentials are included.
- Replicate model input fields vary; configure the chosen model schema before generating clips.
