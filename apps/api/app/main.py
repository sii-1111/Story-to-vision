import re
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.assembly import EpisodeAssemblyError, assemble_episode
from app.config import get_settings, is_local_openai_compatible_url
from app.continuity import build_continuity_report
from app.database import (
    get_project,
    list_projects,
    record_generation_job,
    save_project,
    update_generation_job,
)
from app.models import (
    ContinuityCheckRequest,
    ContinuityCheckResponse,
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
    VisualIdentityCheckRequest,
    VisualIdentityCheckResponse,
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
from app.visual_identity import (
    VisualIdentityNotConfiguredError,
    VisualIdentityProviderError,
    audit_visual_identity,
)

app = FastAPI(
    title="Story-to-Vision API",
    version="0.1.0",
    description="Turn written stories into structured episodic screenplays.",
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/provider-readiness", tags=["system"])
async def provider_readiness() -> dict[str, bool]:
    """Report configuration presence without returning credentials or model secrets."""
    settings = get_settings()
    llm_ready = bool(
        settings.llm_model.strip()
        and (
            settings.llm_api_key.strip()
            or is_local_openai_compatible_url(settings.llm_base_url)
        )
    )
    visual_identity_ready = bool(
        settings.visual_identity_model.strip()
        and (
            settings.llm_api_key.strip()
            or is_local_openai_compatible_url(settings.llm_base_url)
        )
    )
    return {
        "ready_for_screenplay": llm_ready,
        "ready_for_video": bool(
            settings.video_api_token.strip() and settings.video_model.strip()
        ),
        "ready_for_visual_identity": visual_identity_ready,
    }


@app.get("/api/system/local-model-readiness", tags=["system"])
async def local_model_readiness() -> dict[str, bool | str | None]:
    """Check a local OpenAI-compatible model endpoint without generating tokens."""
    settings = get_settings()
    model = settings.llm_model.strip()
    if not is_local_openai_compatible_url(settings.llm_base_url):
        return {
            "is_local_provider": False,
            "configured": bool(model),
            "reachable": None,
            "model_available": None,
            "model": model or None,
            "message": "The configured LLM endpoint is not recognized as a local provider.",
        }
    if not model:
        return {
            "is_local_provider": True,
            "configured": False,
            "reachable": None,
            "model_available": False,
            "model": None,
            "message": "Set LLM_MODEL to the name of a model installed in your local provider.",
        }

    models_url = f"{settings.llm_base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(models_url)
            response.raise_for_status()
            payload = response.json()
        model_entries = payload.get("data", [])
        installed_models = [
            entry.get("id", "")
            for entry in model_entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]
        wanted = model.casefold()
        available = any(
            installed.casefold() == wanted
            or installed.casefold() == f"{wanted}:latest"
            for installed in installed_models
        )
        return {
            "is_local_provider": True,
            "configured": True,
            "reachable": True,
            "model_available": available,
            "model": model,
            "message": (
                "Local model endpoint is reachable and the configured model is available."
                if available
                else "Local endpoint is reachable, but the configured model was not found. "
                "Check LLM_MODEL or download the model first."
            ),
        }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {
            "is_local_provider": True,
            "configured": True,
            "reachable": False,
            "model_available": False,
            "model": model,
            "message": (
                "Could not reach the local model endpoint. Start Ollama or LM Studio and "
                "check LLM_BASE_URL from the API container or host."
            ),
        }

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
    "/api/stories/visual-identity-check",
    response_model=VisualIdentityCheckResponse,
    tags=["stories"],
    summary="Compare generated frame images against canonical character reference images",
)
async def check_visual_identity(
    request: VisualIdentityCheckRequest,
) -> VisualIdentityCheckResponse:
    try:
        report = await audit_visual_identity(get_settings(), request)
    except VisualIdentityNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except VisualIdentityProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return VisualIdentityCheckResponse(**report)


@app.post(
    "/api/stories/continuity-check",
    response_model=ContinuityCheckResponse,
    tags=["stories"],
    summary="Audit character visual anchors and scene continuity before video generation",
)
async def check_story_continuity(
    request: ContinuityCheckRequest,
) -> ContinuityCheckResponse:
    return ContinuityCheckResponse(
        **build_continuity_report(request.screenplay)
    )


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
