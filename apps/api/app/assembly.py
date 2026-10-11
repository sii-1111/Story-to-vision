"""Assemble provider-generated scene clips into a downloadable vertical episode."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import Screenplay
from app.video import ReplicateVideoProvider, VideoProviderError

MAX_CLIP_BYTES = 250 * 1024 * 1024
ALLOWED_VIDEO_HOSTS = ("replicate.delivery",)


class EpisodeAssemblyError(RuntimeError):
    """Raised when clips cannot be safely downloaded or assembled."""


def _is_allowed_video_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(host)
        and any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_VIDEO_HOSTS)
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


async def _download_clip(url: str, destination: Path) -> None:
    if not _is_allowed_video_url(url):
        raise EpisodeAssemblyError(
            "Provider returned a video URL outside the approved delivery domain."
        )
    total = 0
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not (
                    content_type.startswith("video/") or "octet-stream" in content_type
                ):
                    raise EpisodeAssemblyError("Provider output is not a video file.")
                with destination.open("wb") as output:
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_CLIP_BYTES:
                            raise EpisodeAssemblyError(
                                "A generated clip exceeds the 250 MB limit."
                            )
                        output.write(chunk)
    except EpisodeAssemblyError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise EpisodeAssemblyError(
            "Could not download a generated clip. Refresh its provider status and retry."
        ) from exc
    if total == 0:
        raise EpisodeAssemblyError("The provider returned an empty video file.")


def _subtitle_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _write_subtitles(screenplay: Screenplay, path: Path) -> None:
    entries: list[str] = []
    offset_ms = 0
    cue = 1
    for scene in screenplay.scenes:
        scene_duration_ms = scene.duration_seconds * 1000
        dialogue = scene.dialogue
        if dialogue:
            slot_ms = scene_duration_ms // len(dialogue)
            for index, line in enumerate(dialogue):
                start = offset_ms + index * slot_ms
                end = offset_ms + min(scene_duration_ms, (index + 1) * slot_ms)
                safe_line = re.sub(r"[\r\n]+", " ", line).strip()
                entries.append(
                    f"{cue}\n{_subtitle_timestamp(start)} --> "
                    f"{_subtitle_timestamp(end)}\n{safe_line}\n"
                )
                cue += 1
        offset_ms += scene_duration_ms
    path.write_text("\n".join(entries), encoding="utf-8")


async def assemble_episode(
    settings: Settings,
    screenplay: Screenplay,
    job_ids: list[str],
) -> str:
    if len(job_ids) != len(screenplay.scenes):
        raise EpisodeAssemblyError(
            "Provide one completed video job ID for every screenplay scene."
        )
    if len(set(job_ids)) != len(job_ids):
        raise EpisodeAssemblyError("Each scene must reference a distinct video job.")

    provider = ReplicateVideoProvider(settings)
    try:
        jobs = [await provider.retrieve(job_id) for job_id in job_ids]
    except VideoProviderError as exc:
        raise EpisodeAssemblyError(
            "Could not verify every scene's video job. Refresh status and retry."
        ) from exc
    if any(job["status"] != "succeeded" or not job["video_url"] for job in jobs):
        raise EpisodeAssemblyError(
            "Every scene must have a completed video clip before export."
        )

    output_dir = Path(settings.episode_export_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    export_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="stv-") as temporary:
        temp_dir = Path(temporary)
        clips: list[Path] = []
        for index, job in enumerate(jobs, start=1):
            clip = temp_dir / f"clip-{index:02}.mp4"
            await _download_clip(job["video_url"], clip)
            clips.append(clip)

        concat_file = temp_dir / "clips.txt"
        concat_file.write_text(
            "".join(f"file '{clip.as_posix()}'\n" for clip in clips),
            encoding="utf-8",
        )
        subtitles = temp_dir / "dialogue.srt"
        _write_subtitles(screenplay, subtitles)
        destination = output_dir / f"{export_id}.mp4"
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise EpisodeAssemblyError("FFmpeg is not installed on the API server.")
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,fps=30,setsar=1,subtitles=" + str(subtitles),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            "-t",
            str(sum(scene.duration_seconds for scene in screenplay.scenes)),
            str(destination),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except (OSError, asyncio.TimeoutError) as exc:
            destination.unlink(missing_ok=True)
            raise EpisodeAssemblyError(
                "Episode assembly timed out or could not start."
            ) from exc
        if process.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
            destination.unlink(missing_ok=True)
            raise EpisodeAssemblyError(
                "FFmpeg could not assemble the clips. Check that generated clips are compatible."
            )
    return f"/api/episodes/exports/{export_id}.mp4"
