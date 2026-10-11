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
    from app.config import Settings, get_settings

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
