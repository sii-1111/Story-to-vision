"""Technical quality checks for assembled vertical video exports."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any


class VideoQualityError(RuntimeError):
    """Raised when a video cannot be inspected safely."""


async def _run(*command: str, timeout: float = 45) -> tuple[int, str, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (OSError, TimeoutError) as exc:
        raise VideoQualityError("Video inspection tool failed or timed out.") from exc
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "status": "passed" if passed else "failed", "details": details}


async def inspect_video(
    path: str | Path,
    *,
    expected_duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Inspect container metadata and decode the entire video stream."""
    video_path = Path(path)
    if not video_path.is_file() or video_path.stat().st_size < 1024:
        raise VideoQualityError("Video file is missing or too small to be a valid export.")

    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise VideoQualityError("FFmpeg and FFprobe must be installed to inspect video exports.")

    code, stdout, _ = await _run(
        ffprobe,
        "-v", "error",
        "-show_entries",
        "format=duration,format_name,size:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json",
        str(video_path),
    )
    if code != 0:
        raise VideoQualityError("FFprobe could not read the exported video.")
    try:
        metadata = json.loads(stdout)
        streams = metadata.get("streams", [])
        video_stream = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = float(metadata.get("format", {}).get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        codec = str(video_stream.get("codec_name", "unknown"))
        size_bytes = int(metadata.get("format", {}).get("size", video_path.stat().st_size))
        frame_rate = str(video_stream.get("avg_frame_rate", "0/0"))
    except (ValueError, TypeError, KeyError, StopIteration) as exc:
        raise VideoQualityError("Export is missing required video metadata.") from exc

    checks = [
        _check(
            "Video stream",
            width > 0 and height > 0,
            f"Detected {width}×{height} video stream.",
        ),
        _check(
            "Vertical format",
            width == 1080 and height == 1920,
            f"Expected 1080×1920; detected {width}×{height}.",
        ),
        _check("H.264 codec", codec == "h264", f"Detected codec: {codec}."),
        _check("Usable duration", duration >= 1, f"Detected {duration:.2f} seconds."),
    ]
    if expected_duration_seconds is not None:
        tolerance = max(1.25, expected_duration_seconds * 0.08)
        duration_ok = abs(duration - expected_duration_seconds) <= tolerance
        checks.append(
            _check(
                "Duration matches screenplay",
                duration_ok,
                f"Expected about {expected_duration_seconds}s; detected {duration:.2f}s "
                f"(±{tolerance:.2f}s tolerance).",
            )
        )

    decode_code, _, decode_stderr = await _run(
        ffmpeg,
        "-hide_banner",
        "-v", "error",
        "-i", str(video_path),
        "-map", "0:v:0", "-f", "null", "-", timeout=120,
    )
    decode_ok = decode_code == 0 and not decode_stderr.strip()
    checks.append(
        _check(
            "Full video decode",
            decode_ok,
            "The complete video stream decoded without errors."
            if decode_ok else "Decoder reported errors; regenerate or reassemble this episode.",
        )
    )
    scan_code, _, scan_stderr = await _run(
        ffmpeg,
        "-hide_banner",
        "-v", "info",
        "-i", str(video_path),
        "-vf", "blackdetect=d=2:pix_th=0.98,freezedetect=n=-60dB:d=3",
        "-an",
        "-f", "null", "-",
        timeout=120,
    )
    if scan_code != 0:
        checks.append(
            _check(
                "Visual anomaly scan",
                False,
                "FFmpeg could not complete black-frame and frozen-frame analysis.",
            )
        )
    else:
        black_durations = [
            float(value)
            for value in re.findall(r"black_duration:([0-9.]+)", scan_stderr)
        ]
        freeze_durations = [
            float(value)
            for value in re.findall(r"freeze_duration:([0-9.]+)", scan_stderr)
        ]
        checks.append(
            _check(
                "Prolonged black frames",
                not black_durations,
                "No black segment longer than 2 seconds detected."
                if not black_durations
                else f"Detected {len(black_durations)} black segment(s) over 2 seconds; review scene transitions.",
            )
        )
        checks.append(
            _check(
                "Frozen frames",
                not freeze_durations,
                "No frozen segment longer than 3 seconds detected."
                if not freeze_durations
                else f"Detected {len(freeze_durations)} potentially frozen segment(s) over 3 seconds; review for intentional still shots.",
            )
        )
    passed = all(check["status"] == "passed" for check in checks)
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "summary": (
            f"{sum(item['status'] == 'passed' for item in checks)} of "
            f"{len(checks)} checks passed."
        ),
        "duration_seconds": round(duration, 2),
        "width": width,
        "height": height,
        "codec": codec,
        "frame_rate": frame_rate,
        "size_bytes": size_bytes,
        "checks": checks,
    }
