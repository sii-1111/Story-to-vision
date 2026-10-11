"""Vision-model-backed character identity review for generated video frames.

This is an assistive visual comparison, not biometric identification or proof of identity.
Images are sent to the configured vision-capable, OpenAI-compatible model and are not stored.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from app.config import Settings
from app.models import VisualIdentityCheckRequest

MAX_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class VisualIdentityNotConfiguredError(RuntimeError):
    """Raised when a vision-capable provider is not configured."""


class VisualIdentityProviderError(RuntimeError):
    """Raised when the provider response cannot be used."""


def _image_data_url(image_base64: str, mime_type: str) -> str:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Images must be JPEG, PNG, or WebP.")
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Image content must be valid base64.") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Each image must be non-empty and no larger than 4 MiB.")
    return f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"


def build_identity_report_payload(result: dict[str, Any]) -> dict[str, Any]:
    checks = result.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Vision provider returned no identity checks.")
    normalized = []
    for item in checks:
        if not isinstance(item, dict):
            raise ValueError("Vision provider returned an invalid identity check.")
        scene_number = item.get("scene_number")
        character_id = item.get("character_id")
        verdict = item.get("verdict")
        score = item.get("similarity_score")
        if not isinstance(scene_number, int) or not isinstance(character_id, str):
            raise ValueError("Vision provider omitted scene or character identity.")
        if verdict not in {"consistent", "drift_detected", "uncertain"}:
            raise ValueError("Vision provider returned an unsupported verdict.")
        if not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError("Vision provider returned an invalid similarity score.")
        normalized.append({
            "scene_number": scene_number,
            "character_id": character_id,
            "character_name": str(item.get("character_name", character_id)),
            "verdict": verdict,
            "similarity_score": score,
            "matching_observations": [str(x) for x in item.get("matching_observations", [])][:8],
            "differences": [str(x) for x in item.get("differences", [])][:8],
            "recommendation": str(item.get("recommendation", "Review this frame manually."))[:500],
        })
    return {
        "status": "needs_review" if any(x["verdict"] != "consistent" for x in normalized) else "ready_for_review",
        "checks": normalized,
        "summary": f"{sum(x['verdict'] == 'consistent' for x in normalized)} of {len(normalized)} character-frame comparisons were assessed as visually consistent.",
        "limitations": (
            "Scores are model estimates, not calibrated probabilities or biometric identity verification. "
            "Lighting, camera angle, occlusion, animation style, and image quality can affect results. "
            "Review flagged and low-confidence frames manually."
        ),
    }


async def audit_visual_identity(
    settings: Settings, request: VisualIdentityCheckRequest
) -> dict[str, Any]:
    if not settings.llm_api_key.strip() or not settings.visual_identity_model.strip():
        raise VisualIdentityNotConfiguredError(
            "Configure LLM_API_KEY and VISUAL_IDENTITY_MODEL with a vision-capable "
            "OpenAI-compatible model before running visual identity checks."
        )

    characters = {character.id: character for character in request.screenplay.characters}
    references = {image.character_id: image for image in request.references}
    if len(references) != len(request.references):
        raise ValueError("Provide only one reference image per character.")
    unknown = set(references) - set(characters)
    if unknown:
        raise ValueError(f"Reference images contain unknown character IDs: {sorted(unknown)}")
    if not references:
        raise ValueError("Provide at least one character reference image.")
    if not request.frames:
        raise ValueError("Provide at least one generated frame image.")

    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": (
            "Compare each generated frame against the supplied canonical character reference images. "
            "Use only visible evidence: hair, face shape, skin tone, age presentation, and distinctive "
            "accessories/clothing when visible. Do not infer a real person's identity. If obscured or "
            "inconclusive, use uncertain. Similarity score is a subjective 0-100 visual resemblance "
            "estimate, not a probability. Return JSON only with shape: "
            '{"checks":[{"scene_number":1,"character_id":"id","character_name":"name",'
            '"verdict":"consistent|drift_detected|uncertain","similarity_score":0,'
            '"matching_observations":["..."],"differences":["..."],"recommendation":"..."}]}. '
            "Assess only characters explicitly present in each supplied frame's scene."
        ),
    }]
    for character_id, reference in references.items():
        character = characters[character_id]
        content.append({"type": "text", "text": f"CANONICAL REFERENCE for {character.name} ({character_id}). Description: {character.appearance}"})
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_data_url(reference.image_base64, reference.mime_type), "detail": "high"},
        })
    for frame in request.frames:
        scene = request.screenplay.scenes[frame.scene_number - 1]
        present = [characters[cid].name for cid in scene.characters_present if cid in references]
        if not present:
            continue
        content.append({
            "type": "text",
            "text": f"GENERATED FRAME: scene {frame.scene_number}, timestamp {frame.timestamp_seconds}s. Characters to assess: {', '.join(present)}.",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_data_url(frame.image_base64, frame.mime_type), "detail": "high"},
        })
    if len(content) <= 1:
        raise ValueError("No supplied frames contain characters with reference images.")

    payload = {
        "model": settings.visual_identity_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a cautious visual continuity reviewer for fictional video characters."},
            {"role": "user", "content": content},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise ValueError("Vision response content was not text.")
            result = json.loads(raw)
            return build_identity_report_payload(result)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise VisualIdentityProviderError(
            "The vision provider could not complete the identity review. Check model support and provider settings."
        ) from exc
