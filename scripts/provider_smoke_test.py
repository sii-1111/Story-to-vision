#!/usr/bin/env python3
"""Run a safe provider preflight, with optional paid screenplay/video smoke tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx


SAMPLE_STORY = (
    "Mira returns to her coastal hometown after five years and finds an unopened letter "
    "from her childhood friend Arun. As a storm approaches, she learns he is leaving at dawn, "
    "and the letter reveals why he disappeared."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Story-to-Vision provider readiness; paid generation is opt-in."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running Story-to-Vision API.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Call the configured LLM and validate a real generated screenplay (may incur cost).",
    )
    parser.add_argument(
        "--generate-episode",
        action="store_true",
        help="Generate every scene and assemble an MP4 (may incur significant provider cost).",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=900,
        help="Maximum seconds to wait for video jobs (default: 900).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between video status checks (default: 5).",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def run_smoke_test(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print("PASS API health")

        readiness_response = await client.get("/api/system/provider-readiness")
        readiness_response.raise_for_status()
        readiness = readiness_response.json()
        print("Provider readiness:")
        print(json.dumps(readiness, indent=2))
        if not args.plan and not args.generate_episode:
            print("PASS preflight only; no model calls or paid video jobs were submitted.")
            return 0
        require(
            readiness["ready_for_screenplay"],
            "LLM is not configured; set LLM_API_KEY and LLM_MODEL.",
        )
        if args.generate_episode:
            require(
                readiness["ready_for_video"],
                "Video provider is not configured; set VIDEO_API_TOKEN and VIDEO_MODEL.",
            )

        plan_response = await client.post(
            "/api/stories/plan",
            json={
                "title": "The Letter Before Dawn",
                "story": SAMPLE_STORY,
                "genre": "romantic drama",
                "visual_style": "cinematic realism",
                "language": "English",
                "episode_duration_seconds": 45,
            },
        )
        plan_response.raise_for_status()
        screenplay = plan_response.json()["screenplay"]
        scenes = screenplay["scenes"]
        require(4 <= len(scenes) <= 6, "Generated screenplay must contain 4 to 6 scenes.")
        print(f"PASS live LLM screenplay: {len(scenes)} scenes, {screenplay['title']!r}")
        if not args.generate_episode:
            return 0

        job_ids: list[str] = []
        for scene in scenes:
            response = await client.post(
                "/api/videos/jobs",
                json={"screenplay": screenplay, "scene_number": scene["scene_number"]},
            )
            response.raise_for_status()
            job = response.json()
            job_ids.append(job["job_id"])
            print(f"SUBMITTED scene {scene['scene_number']}: {job['job_id']} ({job['status']})")

        deadline = time.monotonic() + args.poll_timeout
        completed: dict[str, dict[str, Any]] = {}
        while len(completed) < len(job_ids):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timed out waiting for video jobs; completed {len(completed)}/{len(job_ids)}. "
                    "Check the provider dashboard before retrying to avoid duplicate charges."
                )
            for scene_number, job_id in enumerate(job_ids, start=1):
                if job_id in completed:
                    continue
                response = await client.get(f"/api/videos/jobs/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] == "succeeded" and job.get("video_url"):
                    completed[job_id] = job
                    print(f"PASS scene {scene_number} video ready")
                elif job["status"] in {"failed", "canceled"}:
                    raise RuntimeError(
                        f"Video job for scene {scene_number} ended as {job['status']}: "
                        f"{job.get('error') or 'no provider error details'}"
                    )
            if len(completed) < len(job_ids):
                await asyncio.sleep(args.poll_interval)

        assembly = await client.post(
            "/api/episodes/assemble",
            json={"screenplay": screenplay, "video_job_ids": job_ids},
            timeout=httpx.Timeout(180.0, connect=10.0),
        )
        assembly.raise_for_status()
        episode = assembly.json()
        print("PASS episode assembled")
        print(json.dumps({
            "episode_id": episode["episode_id"],
            "download_url": episode["download_url"],
            "format": episode["format"],
            "aspect_ratio": episode["aspect_ratio"],
        }, indent=2))
        quality = await client.get(
            f"/api/episodes/exports/{episode['episode_id']}/quality-check",
            timeout=httpx.Timeout(180.0, connect=10.0),
        )
        quality.raise_for_status()
        report = quality.json()
        print("Technical quality report:")
        print(json.dumps(report, indent=2))
        failed_checks = [
            check for check in report.get("checks", [])
            if isinstance(check, dict) and check.get("status") == "failed"
        ]
        if report.get("status") != "passed" or failed_checks:
            print(f"WARNING: {len(failed_checks)} technical quality check(s) failed.")
            return 2
        print("PASS end-to-end provider smoke test")
        return 0


def main() -> None:
    args = parse_args()
    if args.poll_timeout < 1 or args.poll_interval <= 0:
        raise SystemExit("--poll-timeout and --poll-interval must be positive.")
    try:
        exit_code = asyncio.run(run_smoke_test(args))
    except (httpx.HTTPError, KeyError, RuntimeError, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
