import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.assembly import EpisodeAssemblyError, assemble_episode
from app.config import get_settings
from app.database import (
    get_project,
    list_projects,
    record_generation_job,
    save_project,
    update_generation_job,
)
from app.models import (
    EpisodeAssemblyRequest,
    EpisodeAssemblyResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectSaveRequest,
    SceneRegenerationRequest,
    SceneRegenerationResponse,
    StoryPlanResponse,
    StoryRequest,
    VideoGenerationRequest,
    VideoJobResponse,
    VideoQualityResponse,
)
from app.planner import (
    LLMStoryPlanner,
    PlannerNotConfiguredError,
    PlannerUpstreamError,
)
from app.quality import VideoQualityError, inspect_video
from app.video import (
    ReplicateVideoProvider,
    VideoProviderError,
    VideoProviderNotConfiguredError,
    build_scene_prompt,
)

app = FastAPI(
    title="Story-to-Vision API",
    version="0.1.0",
    description="Turn written stories into structured episodic screenplays.",
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/stories/plan",
    response_model=StoryPlanResponse,
    status_code=status.HTTP_200_OK,
    tags=["stories"],
    summary="Plan a story into a short-episode screenplay",
)
async def plan_story(request: StoryRequest) -> StoryPlanResponse:
    planner = LLMStoryPlanner(get_settings())
    try:
        screenplay = await planner.plan(request)
    except PlannerNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PlannerUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return StoryPlanResponse(screenplay=screenplay)



@app.post(
    "/api/stories/regenerate-scene",
    response_model=SceneRegenerationResponse,
    status_code=status.HTTP_200_OK,
    tags=["stories"],
    summary="Regenerate one scene while preserving screenplay continuity",
)
async def regenerate_scene(request: SceneRegenerationRequest) -> SceneRegenerationResponse:
    planner = LLMStoryPlanner(get_settings())
    try:
        scene, notes = await planner.regenerate_scene(
            request.screenplay,
            request.scene_number,
            request.instruction,
        )
    except PlannerNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PlannerUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return SceneRegenerationResponse(scene=scene, continuity_notes=notes)



@app.post(
    "/api/videos/jobs",
    response_model=VideoJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["video"],
    summary="Submit a screenplay scene for direct text-to-video generation",
)
async def create_video_job(request: VideoGenerationRequest) -> VideoJobResponse:
    settings = get_settings()
    if request.project_id:
        try:
            get_project(request.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
    provider = ReplicateVideoProvider(settings)
    scene = request.screenplay.scenes[request.scene_number - 1]

    try:
        result = await provider.submit(
            build_scene_prompt(request.screenplay, scene),
            scene.duration_seconds,
        )
    except VideoProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VideoProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if request.project_id:
        record_generation_job(request.project_id, request.scene_number, result)
    return VideoJobResponse(**result)


@app.get(
    "/api/videos/jobs/{job_id}",
    response_model=VideoJobResponse,
    tags=["video"],
    summary="Check the status of a video generation job",
)
async def get_video_job(job_id: str, project_id: str | None = None) -> VideoJobResponse:
    provider = ReplicateVideoProvider(get_settings())
    try:
        result = await provider.retrieve(job_id)
    except VideoProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VideoProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if project_id:
        update_generation_job(project_id, result)
    return VideoJobResponse(**result)


@app.post(
    "/api/episodes/assemble",
    response_model=EpisodeAssemblyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["episodes"],
    summary="Assemble completed scene clips into a vertical MP4 episode",
)
async def assemble_episode_endpoint(
    request: EpisodeAssemblyRequest,
) -> EpisodeAssemblyResponse:
    try:
        download_url = await assemble_episode(
            get_settings(),
            request.screenplay,
            request.video_job_ids,
        )
    except EpisodeAssemblyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    episode_id = download_url.rsplit("/", maxsplit=1)[-1].removesuffix(".mp4")
    return EpisodeAssemblyResponse(episode_id=episode_id, download_url=download_url)




@app.post(
    "/api/episodes/exports/{episode_id}/quality-check",
    response_model=VideoQualityResponse,
    tags=["episodes"],
    summary="Inspect an exported episode for format, duration, codec, and decode errors",
)
async def check_episode_quality(episode_id: str) -> VideoQualityResponse:
    if not re.fullmatch(r"[a-f0-9]{32}", episode_id):
        raise HTTPException(status_code=404, detail="Episode export not found.")
    settings = get_settings()
    export_path = Path(settings.episode_export_dir).resolve() / f"{episode_id}.mp4"
    if not export_path.is_file():
        raise HTTPException(status_code=404, detail="Episode export not found.")
    try:
        report = await inspect_video(export_path)
    except VideoQualityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return VideoQualityResponse(**report)


@app.get(
    "/api/episodes/exports/{episode_id}/quality-check",
    response_model=VideoQualityResponse,
    tags=["episodes"],
    summary="Retrieve a fresh technical quality report for an exported episode",
)
async def get_episode_quality(episode_id: str) -> VideoQualityResponse:
    return await check_episode_quality(episode_id)

@app.get(
    "/api/episodes/exports/{episode_id}.mp4",
    tags=["episodes"],
    summary="Download an assembled MP4 episode",
)
async def download_episode(episode_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", episode_id):
        raise HTTPException(status_code=404, detail="Episode export not found.")
    export_path = (Path(get_settings().episode_export_dir).resolve() / f"{episode_id}.mp4")
    if not export_path.is_file():
        raise HTTPException(status_code=404, detail="Episode export not found.")
    return FileResponse(
        export_path,
        media_type="video/mp4",
        filename=f"story-to-vision-{episode_id}.mp4",
    )



@app.get(
    "/api/projects",
    response_model=ProjectListResponse,
    tags=["projects"],
    summary="List saved story projects",
)
async def get_projects() -> ProjectListResponse:
    return ProjectListResponse(projects=list_projects())


@app.post(
    "/api/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
    summary="Save a story project and its latest screenplay",
)
async def save_story_project(request: ProjectSaveRequest) -> ProjectResponse:
    try:
        screenplay = request.screenplay.model_dump(mode="json") if request.screenplay else None
        project = save_project(
            title=request.title,
            story=request.story,
            screenplay=screenplay,
            project_id=request.project_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    return ProjectResponse(project=project)


@app.get(
    "/api/projects/{project_id}",
    response_model=ProjectResponse,
    tags=["projects"],
    summary="Load a saved project, screenplay, characters, and generation history",
)
async def load_story_project(project_id: str) -> ProjectResponse:
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        project = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    return ProjectResponse(project=project)

@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Do not leak stack traces, credentials, or provider response bodies to clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
