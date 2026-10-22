#!/usr/bin/env python3
"""Inspect local hardware for free, open-weight video generation; never downloads or calls providers."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str], timeout: int = 5) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def detect_memory_bytes() -> int | None:
    system = platform.system()
    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    if system == "Darwin":
        value = _run(["sysctl", "-n", "hw.memsize"])
        try:
            return int(value) if value else None
        except ValueError:
            return None
    if system == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except (AttributeError, OSError):
            return None
    return None


def detect_nvidia_gpus() -> list[dict[str, Any]]:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return []
    gpus: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.split(",", maxsplit=2)]
        if len(fields) != 3:
            continue
        try:
            vram_mib = int(fields[1])
        except ValueError:
            continue
        gpus.append(
            {
                "name": fields[0],
                "vram_gib": round(vram_mib / 1024, 1),
                "driver_version": fields[2],
            }
        )
    return gpus


def assess_hardware(memory_bytes: int | None, gpus: list[dict[str, Any]]) -> dict[str, Any]:
    system = platform.system()
    memory_gib = round(memory_bytes / (1024**3), 1) if memory_bytes else None
    max_vram = max((gpu["vram_gib"] for gpu in gpus), default=None)

    if max_vram is not None and max_vram >= 24 and (memory_gib is None or memory_gib >= 32):
        tier = "strong_local_video_candidate"
        summary = (
            "Test a local ComfyUI workflow with a suitable LTX-family checkpoint first; "
            "also benchmark Wan TI2V-5B if its runtime fits."
        )
    elif max_vram is not None and max_vram >= 16 and (memory_gib is None or memory_gib >= 24):
        tier = "midrange_local_video_candidate"
        summary = (
            "Start with a quantized/distilled LTX-family workflow at reduced resolution and "
            "short duration. Measure peak VRAM and render time before scaling up."
        )
    elif max_vram is not None and max_vram >= 4:
        tier = "very_low_vram_experimental_only"
        if memory_gib is not None and memory_gib < 16:
            summary = (
                "Do not download a large video checkpoint yet. With 4–6 GiB VRAM and under "
                "16 GiB system RAM, full local video generation is a high-risk experiment. "
                "If testing is essential, investigate a quantized CogVideoX-2B Diffusers path "
                "with CPU offload, but expect slow generation, memory pressure, and possible "
                "out-of-memory failures. Prefer a tiny benchmark only after checking disk space."
            )
        else:
            summary = (
                "Only experimental quantized, CPU-offloaded workflows are worth investigating. "
                "Check exact checkpoint/runtime requirements and start with a tiny test; no "
                "model is confirmed compatible by this preflight."
            )
    elif system == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        tier = "apple_silicon_needs_runtime_check"
        summary = (
            "Check the chosen runtime's current Apple Silicon/MPS support and available unified "
            "memory; do not assume CUDA-only workflows will run."
        )
    else:
        tier = "hardware_not_confirmed"
        summary = (
            "No supported NVIDIA GPU with measurable VRAM was detected. Confirm accelerator "
            "and memory details before choosing a local video checkpoint; this script makes no "
            "hosted-provider calls."
        )

    return {
        "platform": platform.platform(),
        "system_memory_gib": memory_gib,
        "nvidia_gpus": gpus,
        "assessment_tier": tier,
        "recommendation": summary,
        "limitations": [
            "This is a hardware preflight, not a benchmark or guarantee that a model will fit.",
            "Other GPU vendors and shared/unified memory may not be fully detected.",
            "Model weights and runtime dependencies are not downloaded or installed.",
            "No hosted inference provider is contacted and no paid job is submitted.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect local hardware for open-weight video generation without network calls."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON (the default output is also JSON).",
    )
    args = parser.parse_args()
    del args  # Reserved for future output formats; keep CLI extensible.
    report = assess_hardware(detect_memory_bytes(), detect_nvidia_gpus())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
