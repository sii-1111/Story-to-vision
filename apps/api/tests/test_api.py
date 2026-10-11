from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_REQUEST = {
    "title": "The Last Promise",
    "story": (
        "Mira returns to her hometown after five years and discovers a letter "
        "that could change her relationship with her childhood friend."
    ),
}


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_story_request_rejects_too_short_story() -> None:
    response = client.post(
        "/api/stories/plan",
        json={"title": "Short", "story": "Too short"},
    )
    assert response.status_code == 422


def test_planning_requires_provider_configuration(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(llm_api_key="", llm_model=""),
    )
    response = client.post("/api/stories/plan", json=VALID_REQUEST)
    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]


def test_openapi_contains_story_planning_endpoint() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/stories/plan" in response.json()["paths"]


def test_scene_regeneration_rejects_scene_number_outside_screenplay() -> None:
    character = {
        "id": "mira",
        "name": "Mira",
        "age_range": "late 20s",
        "appearance": "Dark wavy hair, warm brown eyes, and a small silver pendant.",
        "personality": "Observant, guarded, and deeply loyal to her family.",
        "relationships": [],
    }
    scenes = [
        {
            "scene_number": number,
            "location": f"Coastal house room {number}",
            "time_of_day": "Evening",
            "duration_seconds": 8,
            "characters_present": ["mira"],
            "action": "Mira studies the old letter, unsure whether to open it.",
            "dialogue": ["Mira: Not again."],
            "emotional_beat": "Uneasy anticipation",
            "visual_direction": "Slow close-up with soft window light and shallow focus.",
            "transition": "Cut to the letter.",
        }
        for number in range(1, 5)
    ]
    screenplay = {
        "title": "The Last Promise",
        "logline": "A returned daughter finds a letter that changes everything.",
        "genre": "drama",
        "language": "English",
        "visual_style": "cinematic realism",
        "characters": [character],
        "scenes": scenes,
        "cliffhanger": "The letter reveals a name Mira never expected to see.",
        "continuity_notes": [],
    }
    response = client.post(
        "/api/stories/regenerate-scene",
        json={"screenplay": screenplay, "scene_number": 5},
    )
    assert response.status_code == 422


def test_openapi_contains_scene_regeneration_endpoint() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/stories/regenerate-scene" in response.json()["paths"]


def test_video_generation_requires_provider_configuration(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(video_api_token="", video_model=""),
    )
    response = client.post(
        "/api/videos/jobs",
        json={"screenplay": _valid_screenplay(), "scene_number": 1},
    )
    assert response.status_code == 503
    assert "VIDEO_API_TOKEN" in response.json()["detail"]


def test_video_generation_rejects_scene_number_outside_screenplay() -> None:
    response = client.post(
        "/api/videos/jobs",
        json={"screenplay": _valid_screenplay(), "scene_number": 5},
    )
    assert response.status_code == 422


def test_openapi_contains_video_job_endpoints() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/videos/jobs" in paths
    assert "/api/videos/jobs/{job_id}" in paths


def _valid_screenplay() -> dict:
    character = {
        "id": "mira",
        "name": "Mira",
        "age_range": "late 20s",
        "appearance": "Dark wavy hair, warm brown eyes, and a small silver pendant.",
        "personality": "Observant, guarded, and deeply loyal to her family.",
        "relationships": [],
    }
    scenes = [
        {
            "scene_number": number,
            "location": f"Coastal house room {number}",
            "time_of_day": "Evening",
            "duration_seconds": 8,
            "characters_present": ["mira"],
            "action": "Mira studies the old letter, unsure whether to open it.",
            "dialogue": ["Mira: Not again."],
            "emotional_beat": "Uneasy anticipation",
            "visual_direction": "Slow close-up with soft window light and shallow focus.",
            "transition": "Cut to the letter.",
        }
        for number in range(1, 5)
    ]
    return {
        "title": "The Last Promise",
        "logline": "A returned daughter finds a letter that changes everything.",
        "genre": "drama",
        "language": "English",
        "visual_style": "cinematic realism",
        "characters": [character],
        "scenes": scenes,
        "cliffhanger": "The letter reveals a name Mira never expected to see.",
        "continuity_notes": [],
    }


def test_video_provider_normalizes_successful_output() -> None:
    from app.video import ReplicateVideoProvider

    result = ReplicateVideoProvider._normalize(
        {
            "id": "prediction_123",
            "status": "succeeded",
            "output": ["https://example.invalid/generated.mp4"],
        }
    )
    assert result == {
        "job_id": "prediction_123",
        "status": "succeeded",
        "video_url": "https://example.invalid/generated.mp4",
        "error": None,
    }


def test_video_prompt_includes_scene_and_character_continuity() -> None:
    from app.models import Screenplay
    from app.video import build_scene_prompt

    screenplay = Screenplay.model_validate(_valid_screenplay())
    prompt = build_scene_prompt(screenplay, screenplay.scenes[0])
    assert "Mira" in prompt
    assert "Dark wavy hair" in prompt
    assert "9:16" in prompt
    assert screenplay.scenes[0].action in prompt
