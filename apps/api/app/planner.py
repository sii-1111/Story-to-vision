import json

import httpx

from app.config import Settings, is_local_openai_compatible_url
from app.models import Screenplay, StoryRequest


SYSTEM_PROMPT = """You are a professional episodic drama screenwriter and visual continuity
supervisor. Convert the supplied story into a shootable screenplay for one
short vertical-video episode. Return ONLY a valid JSON object matching the
requested schema.
Rules:
- Create exactly 5 scenes.
- Copy the supplied scene_duration_targets into each scene's duration_seconds, in order. These targets sum exactly to the requested episode duration; do not alter them.
- Preserve the source story's core intent. Do not invent major facts that contradict it.
- Give each recurring character a stable ID (lowercase snake_case) and
  concrete, repeatable visual traits.
- Keep character appearance, relationships, locations, and timeline consistent across scenes.
- Dialogue must be concise and performable; include natural pauses and emotional subtext.
- Every scene must name only character IDs defined in characters.
- Make the final scene deliver a compelling cliffhanger without resolving every conflict.
- Write all screenplay text in the requested language.
- Include concrete visual directions suitable for direct text-to-video
  generation: framing, movement, lighting, setting, and facial emotion.
JSON shape:
{
  "title": "string",
  "logline": "string",
  "genre": "string",
  "language": "string",
  "visual_style": "string",
  "characters": [{
    "id": "lowercase_snake_case",
    "name": "string",
    "age_range": "string",
    "appearance": "string",
    "personality": "string",
    "relationships": ["string"]
  }],
  "scenes": [{
    "scene_number": 1,
    "location": "string",
    "time_of_day": "string",
    "duration_seconds": 8,
    "characters_present": ["character_id"],
    "action": "string",
    "dialogue": ["string"],
    "emotional_beat": "string",
    "visual_direction": "string",
    "transition": "string"
  }],
  "cliffhanger": "string",
  "continuity_notes": ["string"]
}"""


SCENE_REGENERATION_PROMPT = """You are an episodic drama screenwriter and continuity supervisor.
Rewrite exactly one scene for the supplied screenplay. Return only a JSON object matching the Scene schema.
Preserve the scene number, established character IDs, core story facts, visual style, language, relationships,
timeline, and narrative purpose. Do not introduce unlisted characters. Follow the creator instruction only
where it does not contradict screenplay continuity.
"""


def _scene_duration_targets(episode_duration_seconds: int) -> list[int]:
    base_duration, remainder = divmod(episode_duration_seconds, 5)
    return [
        base_duration + int(index < remainder)
        for index in range(5)
    ]


class PlannerNotConfiguredError(RuntimeError):
    """Raised when no usable LLM credentials/model have been configured."""


class PlannerUpstreamError(RuntimeError):
    """Raised when the configured LLM service cannot produce a valid screenplay."""


class LLMStoryPlanner:
    """Small OpenAI-compatible adapter; the provider can be changed through settings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _llm_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.llm_api_key.strip():
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key.strip()}"
        return headers

    def _llm_is_configured(self) -> bool:
        return bool(
            self.settings.llm_model.strip()
            and (
                self.settings.llm_api_key.strip()
                or is_local_openai_compatible_url(self.settings.llm_base_url)
            )
        )

    async def plan(self, request: StoryRequest) -> Screenplay:
        if not self._llm_is_configured():
            raise PlannerNotConfiguredError(
                "Configure LLM_MODEL in the API environment; local OpenAI-compatible endpoints "
                "such as Ollama or LM Studio may omit LLM_API_KEY."
            )

        payload = {
            "model": self.settings.llm_model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "title": request.title,
                            "story": request.story,
                            "genre": request.genre,
                            "visual_style": request.visual_style,
                            "language": request.language,
                            "episode_duration_seconds": request.episode_duration_seconds,
                            "scene_duration_targets": _scene_duration_targets(
                                request.episode_duration_seconds
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = self._llm_headers()

        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise ValueError("LLM response content was not text")
                screenplay = Screenplay.model_validate_json(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise PlannerUpstreamError(
                "The configured LLM provider did not return a valid screenplay. "
                "Check the provider settings and try again."
            ) from exc

        expected_durations = _scene_duration_targets(request.episode_duration_seconds)
        actual_durations = [scene.duration_seconds for scene in screenplay.scenes]
        if actual_durations != expected_durations:
            raise PlannerUpstreamError(
                "Generated screenplay must contain exactly 5 scenes with durations "
                f"{expected_durations} seconds; received {actual_durations}."
            )

        return screenplay

    async def regenerate_scene(self, screenplay, scene_number: int, instruction: str):
        from app.models import Scene

        if not self._llm_is_configured():
            raise PlannerNotConfiguredError(
                "Configure LLM_MODEL in the API environment; local OpenAI-compatible endpoints "
                "such as Ollama or LM Studio may omit LLM_API_KEY."
            )

        original = next(
            scene for scene in screenplay.scenes if scene.scene_number == scene_number
        )
        payload = {
            "model": self.settings.llm_model,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SCENE_REGENERATION_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "screenplay": screenplay.model_dump(mode="json"),
                            "scene_to_rewrite": original.model_dump(mode="json"),
                            "creator_instruction": instruction,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = self._llm_headers()
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                raw = body["choices"][0]["message"]["content"]
                if not isinstance(raw, str):
                    raise ValueError("LLM response content was not text")
                replacement = Scene.model_validate_json(raw)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise PlannerUpstreamError(
                "The configured LLM provider did not return a valid scene. Please retry."
            ) from exc

        if replacement.scene_number != scene_number:
            raise PlannerUpstreamError("The regenerated scene number did not match the request.")
        known_ids = {character.id for character in screenplay.characters}
        if any(item not in known_ids for item in replacement.characters_present):
            raise PlannerUpstreamError(
                "The regenerated scene referenced a character outside the established cast."
            )
        original_total = sum(scene.duration_seconds for scene in screenplay.scenes)
        proposed_total = original_total - original.duration_seconds + replacement.duration_seconds
        tolerance = max(3, round(original_total * 0.2))
        if abs(proposed_total - original_total) > tolerance:
            raise PlannerUpstreamError(
                "The regenerated scene changes episode duration too much. Please retry."
            )
        return replacement, [
            "Scene regenerated with the existing screenplay and cast context.",
            "Review dialogue, transitions, and visual continuity before video generation.",
        ]
