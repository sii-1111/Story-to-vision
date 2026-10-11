"""Deterministic character-continuity checks for screenplay drafts."""

from __future__ import annotations

import re
from typing import Any

from app.models import Screenplay


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", value)
        if token.lower() not in {"with", "from", "that", "this", "their", "wearing", "character"}
    }


def build_continuity_report(screenplay: Screenplay) -> dict[str, Any]:
    """Check character coverage and whether scenes carry useful visual identity anchors."""
    character_by_id = {character.id: character for character in screenplay.characters}
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_appearances = 0
    anchored_appearances = 0

    for character in screenplay.characters:
        scenes = [
            scene for scene in screenplay.scenes
            if character.id in scene.characters_present
        ]
        appearance_tokens = _tokens(character.appearance)
        # Short lists keep prompts stable and avoid copying an entire biography into every shot.
        anchors = list(dict.fromkeys(
            token for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", character.appearance)
            if token.lower() not in {
                "with", "from", "that", "this", "their", "wearing", "character"
            }
        ))[:8]
        scene_results = []
        for scene in scenes:
            total_appearances += 1
            scene_text = f"{scene.action} {scene.visual_direction}"
            scene_tokens = _tokens(scene_text)
            matched = sorted(appearance_tokens & scene_tokens)
            # The scene prompt always receives the full canonical appearance; this score only
            # indicates whether the screenplay itself repeats recognizable traits.
            anchored = len(matched) >= min(2, len(appearance_tokens))
            if anchored:
                anchored_appearances += 1
            scene_results.append({
                "scene_number": scene.scene_number,
                "anchored": anchored,
                "matched_traits": matched[:6],
                "recommendation": (
                    "Visual direction references character traits."
                    if anchored else
                    f"Add 1–2 stable visual traits for {character.name} to the action "
                    "or camera direction."
                ),
            })
        entries.append({
            "character_id": character.id,
            "name": character.name,
            "appearance": character.appearance,
            "personality": character.personality,
            "visual_anchors": anchors,
            "scene_count": len(scenes),
            "scenes": scene_results,
        })
        if not scenes:
            warnings.append(f"{character.name} does not appear in any planned scene.")
        for result in scene_results:
            if not result["anchored"]:
                warnings.append(
                    f"{character.name} in scene {result['scene_number']} needs "
                    "stronger visual direction."
                )

    score = round(100 * anchored_appearances / total_appearances) if total_appearances else 100
    return {
        "score": score,
        "status": "ready_for_review" if not warnings else "needs_review",
        "summary": (
            f"{anchored_appearances} of {total_appearances} character-scene appearances "
            f"repeat recognizable visual traits in the screenplay."
        ),
        "characters": entries,
        "warnings": warnings,
        "limitations": (
            "This is a text-based continuity audit, not visual face recognition. "
            "Every video prompt receives the canonical character appearance, but generated "
            "pixels must still be reviewed for identity drift."
        ),
    }
