import json

import httpx

from app.config import Settings
from app.models import Screenplay, StoryRequest


SYSTEM_PROMPT = """You are a professional episodic drama screenwriter and visual continuity
supervisor. Convert the supplied story into a shootable screenplay for one
short vertical-video episode. Return ONLY a valid JSON object matching the
requested schema.
Rules:
- Create 4 to 6 scenes; their durations should sum to within 20% of the requested episode duration.
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


class PlannerNotConfiguredError(RuntimeError):
    """Raised when no usable LLM credentials/model have been configured."""


class PlannerUpstreamError(RuntimeError):
    """Raised when the configured LLM service cannot produce a valid screenplay."""


class LLMStoryPlanner:
    """Small OpenAI-compatible adapter; the provider can be changed through settings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def plan(self, request: StoryRequest) -> Screenplay:
        if not self.settings.llm_api_key.strip() or not self.settings.llm_model.strip():
            raise PlannerNotConfiguredError(
                "Configure LLM_API_KEY and LLM_MODEL in the API environment."
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
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}

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

        expected_duration = request.episode_duration_seconds
        actual_duration = sum(scene.duration_seconds for scene in screenplay.scenes)
        tolerance = max(3, round(expected_duration * 0.2))
        if abs(actual_duration - expected_duration) > tolerance:
            raise PlannerUpstreamError(
                f"Generated scene duration ({actual_duration}s) is outside the "
                f"allowed range for a {expected_duration}s episode. Please retry."
            )

        return screenplay
