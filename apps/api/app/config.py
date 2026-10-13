from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_local_openai_compatible_url(url: str) -> bool:
    """Return true for local OpenAI-compatible providers such as Ollama or LM Studio."""
    host = (urlparse(url).hostname or "").lower()
    return host in {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "host.docker.internal",
    } or host.endswith(".local")


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    visual_identity_model: str = ""
    llm_timeout_seconds: float = Field(default=45.0, gt=0, le=180)

    video_api_base_url: str = "https://api.replicate.com/v1"
    video_api_token: str = ""
    video_model: str = ""
    video_timeout_seconds: float = Field(default=60.0, gt=0, le=180)
    video_prompt_field: str = "prompt"
    video_aspect_ratio_field: str = "aspect_ratio"
    video_duration_field: str = "duration"
    episode_export_dir: str = "data/exports"
    database_path: str = "data/story_to_vision.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
