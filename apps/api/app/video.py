"""Replicate video generation adapter with provider credentials kept server-side."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import Settings
from app.models import Screenplay, Scene


class VideoProviderNotConfiguredError(RuntimeError):
    """Raised when the video provider has not been configured."""


class VideoProviderError(RuntimeError):
    """Raised when the provider cannot accept or retrieve a video job."""


def build_scene_prompt(screenplay: Screenplay, scene: Scene) -> str:
    characters = {character.id: character for character in screenplay.characters}
    cast_lines = [
        f"{characters[character_id].name}: {characters[character_id].appearance}. "
        f"Personality: {characters[character_id].personality}."
        for character_id in scene.characters_present
        if character_id in characters
    ]
    cast = "\n".join(cast_lines) or "Use the characters described in the scene."
    dialogue = " ".join(scene.dialogue)
    return (
        "Create one cinematic live-action vertical 9:16 drama clip. "
        "Aim for natural human movement, realistic faces and hands, coherent geography, "
        "subtle facial acting, stable wardrobe and character appearance, and no on-screen text "
        "or watermarks. This is a single continuous shot; do not create a montage.\n"
        f"Series: {screenplay.title}. Genre: {screenplay.genre}. "
        f"Visual style: {screenplay.visual_style}.\n"
        f"Location: {scene.location}. Time: {scene.time_of_day}.\n"
        f"Cast and appearance:\n{cast}\n"
        f"Action: {scene.action}\n"
        f"Emotional beat: {scene.emotional_beat}\n"
        f"Camera and lighting: {scene.visual_direction}\n"
        f"Dialogue for performance reference (audio may not be generated): {dialogue}\n"
        f"Transition intent: {scene.transition}"
    )


class ReplicateVideoProvider:
    """Adapter for Replicate model predictions; model input keys are configurable."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _configuration(self) -> tuple[str, str]:
        token = self.settings.video_api_token.strip()
        model = self.settings.video_model.strip()
        if not token or not model:
            raise VideoProviderNotConfiguredError(
                "Configure VIDEO_API_TOKEN and VIDEO_MODEL on the API server."
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", model):
            raise VideoProviderNotConfiguredError(
                "VIDEO_MODEL must use the Replicate owner/model format."
            )
        return token, model

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def submit(self, prompt: str, duration_seconds: int) -> dict[str, Any]:
        token, model = self._configuration()
        input_payload: dict[str, Any] = {
            self.settings.video_prompt_field: prompt,
        }
        if self.settings.video_aspect_ratio_field.strip():
            input_payload[self.settings.video_aspect_ratio_field.strip()] = "9:16"
        if self.settings.video_duration_field.strip():
            input_payload[self.settings.video_duration_field.strip()] = min(
                max(duration_seconds, 2), 10
            )
        url = f"{self.settings.video_api_base_url.rstrip('/')}/models/{model}/predictions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.video_timeout_seconds) as client:
                response = await client.post(
                    url,
                    headers={**self._headers(token), "Prefer": "wait=1"},
                    json={"input": input_payload},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VideoProviderError(
                "The video provider could not start this job. Check model configuration and retry."
            ) from exc
        if not isinstance(payload, dict) or not payload.get("id"):
            raise VideoProviderError("The video provider returned an invalid job response.")
        return self._normalize(payload)

    async def retrieve(self, job_id: str) -> dict[str, Any]:
        token, _ = self._configuration()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
            raise VideoProviderError("Invalid video job ID.")
        url = f"{self.settings.video_api_base_url.rstrip('/')}/predictions/{job_id}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.video_timeout_seconds) as client:
                response = await client.get(url, headers=self._headers(token))
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VideoProviderError(
                "The video provider could not retrieve this job. Check the job ID and retry."
            ) from exc
        if not isinstance(payload, dict) or not payload.get("id"):
            raise VideoProviderError("The video provider returned an invalid job response.")
        return self._normalize(payload)

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        output = payload.get("output")
        video_url = None
        if isinstance(output, str) and output.startswith(("https://", "http://")):
            video_url = output
        elif isinstance(output, list):
            video_url = next(
                (
                    item
                    for item in output
                    if isinstance(item, str) and item.startswith(("https://", "http://"))
                ),
                None,
            )
        status_value = str(payload.get("status", "unknown")).lower()
        if status_value not in {"starting", "processing", "succeeded", "failed", "canceled"}:
            status_value = "queued" if status_value == "created" else "unknown"
        return {
            "job_id": str(payload["id"]),
            "status": status_value,
            "video_url": video_url if status_value == "succeeded" else None,
            "error": (
                "The provider could not generate this clip. Review prompt/model settings and retry."
                if status_value == "failed"
                else None
            ),
        }
