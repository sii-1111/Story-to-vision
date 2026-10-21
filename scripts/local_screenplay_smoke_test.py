#!/usr/bin/env python3
"""Generate and validate one screenplay using only a configured local LLM."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.models import Screenplay  # noqa: E402

SAMPLE_STORY = (
    "Mira returns to her coastal hometown after five years and finds an unopened letter "
    "from her childhood friend Arun. As a storm approaches, she learns he is leaving at dawn, "
    "and the letter reveals why he disappeared."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a live screenplay generation test against a local model only."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running Story-to-Vision API.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=300,
        help="Maximum seconds to wait for local screenplay generation (default: 300).",
    )
    return parser.parse_args()


def validate_screenplay(payload: object) -> Screenplay:
    """Validate the API response again client-side and enforce the smoke-test contract."""
    screenplay = Screenplay.model_validate(payload)
    if len(screenplay.scenes) != 5:
        raise ValueError(f"Expected exactly 5 scenes; received {len(screenplay.scenes)}.")
    durations = [scene.duration_seconds for scene in screenplay.scenes]
    if sum(durations) != 45:
        raise ValueError(f"Expected scene durations to sum to 45 seconds; received {durations}.")
    if [scene.scene_number for scene in screenplay.scenes] != [1, 2, 3, 4, 5]:
        raise ValueError("Scene numbers must be sequential from 1 through 5.")
    return screenplay


async def run_smoke_test(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(15.0, connect=5.0),
    ) as client:
        health_response = await client.get("/health")
        health_response.raise_for_status()
        print("PASS API health")

        readiness_response = await client.get("/api/system/local-model-readiness")
        readiness_response.raise_for_status()
        readiness = readiness_response.json()
        print("Local model readiness:")
        print(json.dumps(readiness, indent=2))
        required = ("is_local_provider", "configured", "reachable", "model_available")
        failed = [key for key in required if readiness.get(key) is not True]
        if failed:
            raise RuntimeError(
                "Refusing to generate: local provider readiness checks failed for "
                f"{', '.join(failed)}. Configure and start Ollama/LM Studio and install "
                "the model first. This script never falls back to a hosted provider."
            )

        response = await client.post(
            "/api/stories/plan",
            json={
                "title": "The Letter Before Dawn",
                "story": SAMPLE_STORY,
                "genre": "romantic drama",
                "visual_style": "cinematic realism",
                "language": "English",
                "episode_duration_seconds": 45,
            },
            timeout=httpx.Timeout(args.request_timeout, connect=5.0),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("screenplay"), dict):
            raise ValueError("API response did not contain a screenplay object.")
        screenplay = validate_screenplay(body["screenplay"])

        result = {
            "status": "passed",
            "provider": "local",
            "model": readiness.get("model"),
            "title": screenplay.title,
            "scene_count": len(screenplay.scenes),
            "scene_durations_seconds": [
                scene.duration_seconds for scene in screenplay.scenes
            ],
            "character_count": len(screenplay.characters),
            "character_ids": [character.id for character in screenplay.characters],
            "schema_validation": "passed",
        }
        print("PASS local screenplay generation and schema validation")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0


def main() -> None:
    args = parse_args()
    if args.request_timeout < 1:
        raise SystemExit("--request-timeout must be positive.")
    try:
        raise SystemExit(asyncio.run(run_smoke_test(args)))
    except (httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
