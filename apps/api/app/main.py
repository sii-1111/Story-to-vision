from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import (
    SceneRegenerationRequest,
    SceneRegenerationResponse,
    StoryPlanResponse,
    StoryRequest,
    VideoGenerationRequest,
    VideoJobResponse,
)
from app.video import (
    ReplicateVideoProvider,
    VideoProviderError,
    VideoProviderNotConfiguredError,
)
from app.planner import (
    LLMStoryPlanner,
    PlannerNotConfiguredError,
    PlannerUpstreamError,
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
    provider = ReplicateVideoProvider(settings)
    scene = request.screenplay.scenes[request.scene_number - 1]
    from app.video import build_scene_prompt

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
    return VideoJobResponse(**result)


@app.get(
    "/api/videos/jobs/{job_id}",
    response_model=VideoJobResponse,
    tags=["video"],
    summary="Check the status of a video generation job",
)
async def get_video_job(job_id: str) -> VideoJobResponse:
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
    return VideoJobResponse(**result)

@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Do not leak stack traces, credentials, or provider response bodies to clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
