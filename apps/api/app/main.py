from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import (
    SceneRegenerationRequest,
    SceneRegenerationResponse,
    StoryPlanResponse,
    StoryRequest,
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

@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Do not leak stack traces, credentials, or provider response bodies to clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
