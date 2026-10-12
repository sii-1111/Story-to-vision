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


def test_local_llm_endpoint_is_ready_without_api_key(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            llm_base_url="http://localhost:11434/v1",
            llm_api_key="",
            llm_model="llama3.1",
        ),
    )
    response = client.get("/api/system/provider-readiness")
    assert response.status_code == 200
    assert response.json()["ready_for_screenplay"] is True


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


def test_episode_assembly_requires_one_job_per_scene() -> None:
    response = client.post(
        "/api/episodes/assemble",
        json={"screenplay": _valid_screenplay(), "video_job_ids": ["one"]},
    )
    assert response.status_code == 422


def test_episode_download_rejects_invalid_export_id() -> None:
    response = client.get("/api/episodes/exports/../../etc/passwd.mp4")
    assert response.status_code in {404, 422}


def test_episode_download_returns_not_found_for_missing_export(monkeypatch, tmp_path) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(episode_export_dir=str(tmp_path)),
    )
    response = client.get("/api/episodes/exports/0123456789abcdef0123456789abcdef.mp4")
    assert response.status_code == 404


def test_episode_export_accepts_only_replicate_delivery_urls() -> None:
    from app.assembly import _is_allowed_video_url

    assert _is_allowed_video_url("https://replicate.delivery/example/clip.mp4")
    assert _is_allowed_video_url("https://cdn.replicate.delivery/example/clip.mp4")
    assert not _is_allowed_video_url("http://replicate.delivery/example/clip.mp4")
    assert not _is_allowed_video_url("https://replicate.delivery.attacker.invalid/clip.mp4")
    assert not _is_allowed_video_url("https://user@replicate.delivery/clip.mp4")


def test_subtitles_follow_scene_offsets_and_dialogue_order(tmp_path) -> None:
    from app.assembly import _write_subtitles
    from app.models import Screenplay

    screenplay = Screenplay.model_validate(_valid_screenplay())
    path = tmp_path / "dialogue.srt"
    _write_subtitles(screenplay, path)
    subtitles = path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:08,000" in subtitles
    assert "Mira: Not again." in subtitles
    assert "00:00:08,000 --> 00:00:16,000" in subtitles


def test_openapi_contains_episode_assembly_and_download_routes() -> None:
    response = client.get("/openapi.json")
    paths = response.json()["paths"]
    assert "/api/episodes/assemble" in paths
    assert "/api/episodes/exports/{episode_id}.mp4" in paths


def test_projects_save_list_restore_screenplay_and_characters(monkeypatch, tmp_path) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(database_path=str(tmp_path / "projects.sqlite3")),
    )
    response = client.post(
        "/api/projects",
        json={
            "title": "The Last Promise",
            "story": VALID_REQUEST["story"],
            "screenplay": _valid_screenplay(),
        },
    )
    assert response.status_code == 201
    project = response.json()["project"]
    project_id = project["id"]
    assert project["episode_count"] == 1
    assert project["character_count"] == 1
    assert project["episodes"][0]["screenplay"]["title"] == "The Last Promise"
    assert project["characters"][0]["id"] == "mira"

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()["projects"][0]["id"] == project_id

    restored = client.get(f"/api/projects/{project_id}")
    assert restored.status_code == 200
    assert restored.json()["project"]["episodes"][0]["screenplay"]["scenes"][0]["scene_number"] == 1


def test_saving_existing_project_updates_latest_screenplay_not_duplicate(
    monkeypatch, tmp_path
) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.database.get_settings",
        lambda: Settings(database_path=str(tmp_path / "projects.sqlite3")),
    )
    first = client.post(
        "/api/projects",
        json={
            "title": "The Last Promise",
            "story": VALID_REQUEST["story"],
            "screenplay": _valid_screenplay(),
        },
    )
    assert first.status_code == 201
    project_id = first.json()["project"]["id"]
    updated_screenplay = _valid_screenplay()
    updated_screenplay["title"] = "The Last Promise — Revised"
    second = client.post(
        "/api/projects",
        json={
            "title": "The Last Promise",
            "story": VALID_REQUEST["story"],
            "screenplay": updated_screenplay,
            "project_id": project_id,
        },
    )
    assert second.status_code == 201
    assert second.json()["project"]["episode_count"] == 1
    assert second.json()["project"]["episodes"][0]["title"] == "The Last Promise — Revised"


def test_project_lookup_returns_404_for_unknown_project() -> None:
    response = client.get("/api/projects/0123456789abcdef0123456789abcdef")
    assert response.status_code == 404


def test_project_save_rejects_invalid_project_id() -> None:
    response = client.post(
        "/api/projects",
        json={
            "title": "The Last Promise",
            "story": VALID_REQUEST["story"],
            "project_id": "not-an-id",
        },
    )
    assert response.status_code == 422


def test_openapi_contains_project_persistence_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/projects" in paths
    assert "/api/projects/{project_id}" in paths


def test_episode_quality_endpoint_rejects_invalid_export_id() -> None:
    response = client.get("/api/episodes/exports/not-an-id/quality-check")
    assert response.status_code == 404


def test_episode_quality_endpoint_returns_structured_report(monkeypatch, tmp_path) -> None:
    from app.config import Settings

    report = {
        "status": "passed",
        "passed": True,
        "summary": "5 of 5 checks passed.",
        "duration_seconds": 32.0,
        "width": 1080,
        "height": 1920,
        "codec": "h264",
        "frame_rate": "30/1",
        "size_bytes": 2048,
        "checks": [
            {
                "name": "Video stream",
                "status": "passed",
                "details": "Detected 1080×1920 video stream.",
            }
        ],
    }
    export_id = "a" * 32
    (tmp_path / f"{export_id}.mp4").write_bytes(b"x" * 2048)
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(episode_export_dir=str(tmp_path)),
    )

    async def fake_inspect_video(path):
        assert path == tmp_path / f"{export_id}.mp4"
        return report

    monkeypatch.setattr("app.main.inspect_video", fake_inspect_video)
    response = client.get(f"/api/episodes/exports/{export_id}/quality-check")
    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    assert response.json()["checks"][0]["name"] == "Video stream"


def test_episode_quality_endpoint_returns_404_for_missing_export(monkeypatch, tmp_path) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(episode_export_dir=str(tmp_path)),
    )
    response = client.get(f"/api/episodes/exports/{'b' * 32}/quality-check")
    assert response.status_code == 404


def test_quality_inspector_flags_wrong_aspect_ratio_and_decode_errors(
    monkeypatch, tmp_path
) -> None:
    import asyncio
    import json

    from app.quality import inspect_video

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"x" * 2048)
    monkeypatch.setattr("app.quality.shutil.which", lambda name: f"/usr/bin/{name}")

    async def fake_run(*command, timeout=45):
        if "-show_entries" in command:
            return (
                0,
                json.dumps({
                    "format": {"duration": "12.0", "size": "2048", "format_name": "mov,mp4"},
                    "streams": [{
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 640,
                        "height": 360,
                        "avg_frame_rate": "24/1",
                    }],
                }),
                "",
            )
        return 1, "", "decode error: invalid frame"

    monkeypatch.setattr("app.quality._run", fake_run)
    report = asyncio.run(inspect_video(video_path, expected_duration_seconds=12))
    assert report["status"] == "failed"
    assert report["passed"] is False
    vertical = next(check for check in report["checks"] if check["name"] == "Vertical format")
    assert vertical["status"] == "failed"
    decoding = next(check for check in report["checks"] if check["name"] == "Full video decode")
    assert decoding["status"] == "failed"


def test_quality_inspector_reports_success_for_valid_video_metadata(monkeypatch, tmp_path) -> None:
    import asyncio
    import json

    from app.quality import inspect_video

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"x" * 2048)
    monkeypatch.setattr("app.quality.shutil.which", lambda name: f"/usr/bin/{name}")

    async def fake_run(*command, timeout=45):
        if "-show_entries" in command:
            return (
                0,
                json.dumps({
                    "format": {"duration": "12.0", "size": "2048", "format_name": "mov,mp4"},
                    "streams": [{
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1080,
                        "height": 1920,
                        "avg_frame_rate": "30/1",
                    }],
                }),
                "",
            )
        return 0, "", ""

    monkeypatch.setattr("app.quality._run", fake_run)
    report = asyncio.run(inspect_video(video_path, expected_duration_seconds=12))
    assert report["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["checks"])


def test_quality_inspector_rejects_missing_export(tmp_path) -> None:
    import asyncio

    import pytest

    from app.quality import VideoQualityError, inspect_video

    with pytest.raises(VideoQualityError, match="missing or too small"):
        asyncio.run(inspect_video(tmp_path / "missing.mp4"))


def test_openapi_contains_episode_quality_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/episodes/exports/{episode_id}/quality-check" in paths


def test_quality_inspector_flags_prolonged_black_and_frozen_segments(monkeypatch, tmp_path) -> None:
    import asyncio
    import json

    from app.quality import inspect_video

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"x" * 2048)
    monkeypatch.setattr("app.quality.shutil.which", lambda name: f"/usr/bin/{name}")

    async def fake_run(*command, timeout=45):
        if "-show_entries" in command:
            return (
                0,
                json.dumps({
                    "format": {"duration": "12.0", "size": "2048"},
                    "streams": [{
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1080,
                        "height": 1920,
                        "avg_frame_rate": "30/1",
                    }],
                }),
                "",
            )
        if "-vf" in command:
            return (
                0,
                "",
                "[blackdetect] black_start:2 black_end:5 black_duration:3.0\\n"
                "[freezedetect] freeze_start:6 freeze_end:10 freeze_duration:4.0",
            )
        return 0, "", ""

    monkeypatch.setattr("app.quality._run", fake_run)
    report = asyncio.run(inspect_video(video_path, expected_duration_seconds=12))
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["Prolonged black frames"]["status"] == "failed"
    assert checks["Frozen frames"]["status"] == "failed"
    assert report["status"] == "failed"


def test_quality_inspector_passes_visual_scan_without_long_black_or_freeze(
    monkeypatch, tmp_path
) -> None:
    import asyncio
    import json

    from app.quality import inspect_video

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"x" * 2048)
    monkeypatch.setattr("app.quality.shutil.which", lambda name: f"/usr/bin/{name}")

    async def fake_run(*command, timeout=45):
        if "-show_entries" in command:
            return (
                0,
                json.dumps({
                    "format": {"duration": "12.0", "size": "2048"},
                    "streams": [{
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1080,
                        "height": 1920,
                        "avg_frame_rate": "30/1",
                    }],
                }),
                "",
            )
        return 0, "", ""

    monkeypatch.setattr("app.quality._run", fake_run)
    report = asyncio.run(inspect_video(video_path, expected_duration_seconds=12))
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["Prolonged black frames"]["status"] == "passed"
    assert checks["Frozen frames"]["status"] == "passed"


def test_character_continuity_audit_returns_visual_anchors_and_scene_warnings() -> None:
    response = client.post(
        "/api/stories/continuity-check",
        json={"screenplay": _valid_screenplay()},
    )
    assert response.status_code == 200
    report = response.json()
    assert 0 <= report["score"] <= 100
    assert report["status"] in {"ready_for_review", "needs_review"}
    assert report["characters"]
    assert report["characters"][0]["visual_anchors"]
    assert report["characters"][0]["scenes"]
    assert "not visual face recognition" in report["limitations"]


def test_character_continuity_audit_rejects_invalid_screenplay() -> None:
    response = client.post(
        "/api/stories/continuity-check",
        json={"screenplay": {"title": "Missing required screenplay fields"}},
    )
    assert response.status_code == 422


def test_openapi_contains_character_continuity_endpoint() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/stories/continuity-check" in paths


def test_visual_identity_endpoint_requires_vision_model_configuration(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(llm_api_key="test-key", visual_identity_model=""),
    )
    response = client.post(
        "/api/stories/visual-identity-check",
        json={
            "screenplay": _valid_screenplay(),
            "references": [{
                "character_id": "mira",
                "image_base64": "aGVsbG8=",
                "mime_type": "image/jpeg",
            }],
            "frames": [{"scene_number": 1, "image_base64": "aGVsbG8=", "mime_type": "image/jpeg"}],
        },
    )
    assert response.status_code == 503
    assert "VISUAL_IDENTITY_MODEL" in response.json()["detail"]


def test_visual_identity_endpoint_validates_unknown_reference_character() -> None:
    response = client.post(
        "/api/stories/visual-identity-check",
        json={
            "screenplay": _valid_screenplay(),
            "references": [{"character_id": "unknown", "image_base64": "aGVsbG8="}],
            "frames": [{"scene_number": 1, "image_base64": "aGVsbG8="}],
        },
    )
    assert response.status_code == 422


def test_visual_identity_report_normalizes_model_output() -> None:
    from app.visual_identity import build_identity_report_payload

    report = build_identity_report_payload({
        "checks": [{
            "scene_number": 1,
            "character_id": "mira",
            "character_name": "Mira",
            "verdict": "drift_detected",
            "similarity_score": 42,
            "matching_observations": ["dark hair"],
            "differences": ["pendant not visible"],
            "recommendation": "Review the frame.",
        }]
    })
    assert report["status"] == "needs_review"
    assert report["checks"][0]["similarity_score"] == 42
    assert report["checks"][0]["verdict"] == "drift_detected"


def test_visual_identity_report_rejects_invalid_provider_verdict() -> None:
    import pytest

    from app.visual_identity import build_identity_report_payload

    with pytest.raises(ValueError, match="unsupported verdict"):
        build_identity_report_payload({
            "checks": [{
                "scene_number": 1,
                "character_id": "mira",
                "verdict": "definitely_same_person",
                "similarity_score": 100,
            }]
        })


def test_visual_identity_endpoint_is_documented_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/stories/visual-identity-check" in paths


def test_provider_readiness_reports_configuration_without_secrets(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            llm_api_key="secret-llm",
            llm_model="text-model",
            video_api_token="secret-video",
            video_model="owner/video-model",
            visual_identity_model="vision-model",
        ),
    )
    response = client.get("/api/system/provider-readiness")
    assert response.status_code == 200
    assert response.json() == {
        "ready_for_screenplay": True,
        "ready_for_video": True,
        "ready_for_visual_identity": True,
    }
    assert "secret-llm" not in response.text
    assert "secret-video" not in response.text


def test_provider_readiness_reports_missing_configuration(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr("app.main.get_settings", lambda: Settings())
    response = client.get("/api/system/provider-readiness")
    assert response.status_code == 200
    assert response.json() == {
        "ready_for_screenplay": False,
        "ready_for_video": False,
        "ready_for_visual_identity": False,
    }
