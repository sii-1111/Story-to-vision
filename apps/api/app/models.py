from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StoryRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    story: str = Field(min_length=30, max_length=20_000)
    genre: str = Field(default="romance", min_length=2, max_length=40)
    visual_style: str = Field(default="cinematic realism", min_length=2, max_length=80)
    language: str = Field(default="English", min_length=2, max_length=40)
    episode_duration_seconds: int = Field(default=45, ge=15, le=90)


class Character(BaseModel):
    id: str = Field(min_length=1, max_length=40, description="Stable ID used across episodes")
    name: str = Field(min_length=1, max_length=80)
    age_range: str = Field(min_length=1, max_length=40)
    appearance: str = Field(min_length=10, max_length=800)
    personality: str = Field(min_length=10, max_length=500)
    relationships: list[str] = Field(default_factory=list, max_length=12)


class Scene(BaseModel):
    scene_number: int = Field(ge=1, le=10)
    location: str = Field(min_length=2, max_length=160)
    time_of_day: str = Field(min_length=2, max_length=40)
    duration_seconds: int = Field(ge=2, le=30)
    characters_present: list[str] = Field(min_length=1, max_length=8)
    action: str = Field(min_length=10, max_length=1200)
    dialogue: list[str] = Field(default_factory=list, max_length=20)
    emotional_beat: str = Field(min_length=2, max_length=200)
    visual_direction: str = Field(min_length=10, max_length=1000)
    transition: str = Field(min_length=2, max_length=160)


class Screenplay(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    logline: str = Field(min_length=10, max_length=300)
    genre: str = Field(min_length=2, max_length=40)
    language: str = Field(min_length=2, max_length=40)
    visual_style: str = Field(min_length=2, max_length=80)
    characters: list[Character] = Field(min_length=1, max_length=8)
    scenes: list[Scene] = Field(min_length=4, max_length=6)
    cliffhanger: str = Field(min_length=10, max_length=500)
    continuity_notes: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("scenes")
    @classmethod
    def scene_numbers_are_sequential(cls, scenes: list[Scene]) -> list[Scene]:
        expected = list(range(1, len(scenes) + 1))
        actual = [scene.scene_number for scene in scenes]
        if actual != expected:
            raise ValueError("scene_number values must be sequential starting at 1")
        return scenes

    @model_validator(mode="after")
    def scene_character_ids_must_exist(self) -> "Screenplay":
        known_ids = {character.id for character in self.characters}
        if len(known_ids) != len(self.characters):
            raise ValueError("character IDs must be unique")
        unknown = {
            character_id
            for scene in self.scenes
            for character_id in scene.characters_present
            if character_id not in known_ids
        }
        if unknown:
            raise ValueError(f"scenes reference unknown character IDs: {sorted(unknown)}")
        return self


class StoryPlanResponse(BaseModel):
    status: Literal["completed"] = "completed"
    screenplay: Screenplay


class SceneRegenerationRequest(BaseModel):
    screenplay: Screenplay
    scene_number: int = Field(ge=1, le=6)
    instruction: str = Field(
        default="Improve the scene while preserving story continuity.",
        min_length=5,
        max_length=500,
    )

    @model_validator(mode="after")
    def requested_scene_must_exist(self) -> "SceneRegenerationRequest":
        if self.scene_number > len(self.screenplay.scenes):
            raise ValueError("scene_number must refer to a scene in the supplied screenplay")
        return self


class SceneRegenerationResponse(BaseModel):
    status: Literal["completed"] = "completed"
    scene: Scene
    continuity_notes: list[str] = Field(default_factory=list, max_length=12)


class VideoGenerationRequest(BaseModel):
    screenplay: Screenplay
    scene_number: int = Field(ge=1, le=6)
    project_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @model_validator(mode="after")
    def requested_scene_must_exist(self) -> "VideoGenerationRequest":
        if self.scene_number > len(self.screenplay.scenes):
            raise ValueError("scene_number must refer to a scene in the supplied screenplay")
        return self


class VideoJobResponse(BaseModel):
    job_id: str
    status: Literal[
        "queued", "starting", "processing", "succeeded", "failed", "canceled", "unknown"
    ]
    video_url: str | None = None
    error: str | None = None


class EpisodeAssemblyRequest(BaseModel):
    screenplay: Screenplay
    video_job_ids: list[str] = Field(min_length=4, max_length=6)

    @model_validator(mode="after")
    def jobs_match_scenes(self) -> "EpisodeAssemblyRequest":
        if len(self.video_job_ids) != len(self.screenplay.scenes):
            raise ValueError("Provide exactly one video job ID for every screenplay scene")
        if len(set(self.video_job_ids)) != len(self.video_job_ids):
            raise ValueError("Each scene must reference a distinct video job")
        if any(not job_id.strip() for job_id in self.video_job_ids):
            raise ValueError("Video job IDs must not be blank")
        return self


class EpisodeAssemblyResponse(BaseModel):
    status: Literal["completed"] = "completed"
    episode_id: str
    download_url: str
    format: Literal["mp4"] = "mp4"
    aspect_ratio: Literal["9:16"] = "9:16"
    subtitles_included: bool = True


class ProjectSaveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    story: str = Field(min_length=30, max_length=20_000)
    screenplay: Screenplay | None = None
    project_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ProjectSummary(BaseModel):
    id: str
    title: str
    story: str
    genre: str
    visual_style: str
    language: str
    created_at: str
    updated_at: str
    episode_count: int = 0
    character_count: int = 0


class ProjectDetail(ProjectSummary):
    episodes: list[dict] = Field(default_factory=list)
    characters: list[dict] = Field(default_factory=list)
    generation_jobs: list[dict] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class ProjectResponse(BaseModel):
    project: ProjectDetail


class VideoQualityCheck(BaseModel):
    name: str
    status: Literal["passed", "failed"]
    details: str


class VideoQualityResponse(BaseModel):
    status: Literal["passed", "failed"]
    passed: bool
    summary: str
    duration_seconds: float
    width: int
    height: int
    codec: str
    frame_rate: str
    size_bytes: int
    checks: list[VideoQualityCheck]


class ContinuityCheckRequest(BaseModel):
    screenplay: Screenplay


class CharacterContinuityScene(BaseModel):
    scene_number: int
    anchored: bool
    matched_traits: list[str]
    recommendation: str


class CharacterContinuityEntry(BaseModel):
    character_id: str
    name: str
    appearance: str
    personality: str
    visual_anchors: list[str]
    scene_count: int
    scenes: list[CharacterContinuityScene]


class ContinuityCheckResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["ready_for_review", "needs_review"]
    summary: str
    characters: list[CharacterContinuityEntry]
    warnings: list[str]
    limitations: str


class VisualReferenceImage(BaseModel):
    character_id: str = Field(min_length=1, max_length=40)
    image_base64: str = Field(min_length=4, max_length=5_600_000)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"


class VisualFrameImage(BaseModel):
    scene_number: int = Field(ge=1, le=6)
    timestamp_seconds: float = Field(default=0, ge=0, le=90)
    image_base64: str = Field(min_length=4, max_length=5_600_000)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"


class VisualIdentityCheckRequest(BaseModel):
    screenplay: Screenplay
    references: list[VisualReferenceImage] = Field(min_length=1, max_length=8)
    frames: list[VisualFrameImage] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_frame_scenes_and_references(self) -> "VisualIdentityCheckRequest":
        known_ids = {character.id for character in self.screenplay.characters}
        if any(reference.character_id not in known_ids for reference in self.references):
            raise ValueError("Reference images must use character IDs from the screenplay.")
        if len({reference.character_id for reference in self.references}) != len(self.references):
            raise ValueError("Provide at most one reference image per character.")
        if any(frame.scene_number > len(self.screenplay.scenes) for frame in self.frames):
            raise ValueError("Each frame scene_number must exist in the supplied screenplay.")
        return self


class VisualIdentityCheck(BaseModel):
    scene_number: int
    character_id: str
    character_name: str
    verdict: Literal["consistent", "drift_detected", "uncertain"]
    similarity_score: int = Field(ge=0, le=100)
    matching_observations: list[str] = Field(default_factory=list, max_length=8)
    differences: list[str] = Field(default_factory=list, max_length=8)
    recommendation: str


class VisualIdentityCheckResponse(BaseModel):
    status: Literal["ready_for_review", "needs_review"]
    checks: list[VisualIdentityCheck]
    summary: str
    limitations: str
