"""
Purpose: Assesses each stored service image with a real local Ollama vision model
and combines semantic relevance/spam findings with deterministic duplicate checks.
"""

import base64
import os
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .uploads import resolve_upload

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream:1.8b")
VISION_TIMEOUT = float(os.getenv("VISION_TIMEOUT_SECONDS", "1000"))


class VisionResult(BaseModel):
    relevance: Literal["relevant", "irrelevant"]
    spam_detected: bool
    confidence: int = Field(ge=0, le=100)
    detected_content: str = Field(min_length=2, max_length=240)
    relevance_reason: str = Field(min_length=3, max_length=240)
    spam_reason: str = Field(min_length=3, max_length=240)


# Uses the configured vision model to inspect actual pixels for relevance and visual spam.
def assess_image_semantics(image: dict, vendor_context: dict) -> dict:
    """Return a validated visual classification or an explicit unavailable state."""
    try:
        encoded = base64.b64encode(resolve_upload(image["storage_name"]).read_bytes()).decode("ascii")
        context = {key: vendor_context.get(key) for key in ("category", "service_title", "description", "package_name", "package_details", "special_offer")}
        prompt = ("Inspect this vendor service image. Decide whether its visible content is relevant to the submitted event service. "
                  "Detect visual spam including unrelated advertising, QR/payment diversion, excessive promotional text, fake guarantees, "
                  "contact diversion, scams, or misleading offers. Do not infer facts that are not visible. Vendor context: " + str(context))
        response = httpx.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", timeout=VISION_TIMEOUT, json={
            "model": VISION_MODEL, "stream": False, "format": VisionResult.model_json_schema(),
            "options": {"temperature": 0, "num_predict": 220},
            "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
        })
        response.raise_for_status()
        parsed = VisionResult.model_validate_json(response.json()["message"]["content"])
        return {"status": "complete", "model": VISION_MODEL, **parsed.model_dump()}
    except (OSError, httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
        return {"status": "unavailable", "model": VISION_MODEL, "relevance": "unavailable", "spam_detected": None,
                "confidence": 0, "detected_content": "Not assessed", "relevance_reason": "Local vision assessment unavailable.",
                "spam_reason": f"{type(exc).__name__}; install and run the configured Ollama vision model."}


# Assesses all images and always records integrity and cross-submission duplication results.
def assess_submission_images(images: list[dict], vendor_context: dict, prior_hashes: set[str]) -> list[dict]:
    """Produce one persisted, auditable result for every uploaded image."""
    seen: set[str] = set()
    results = []
    for image in images:
        fingerprint = image.get("sha256")
        duplicate = bool(fingerprint and (fingerprint in seen or fingerprint in prior_hashes))
        if fingerprint:
            seen.add(fingerprint)
        semantic = assess_image_semantics(image, vendor_context)
        results.append({"storage_name": image["storage_name"], "original_name": image["original_name"],
                        "integrity_verified": bool(image.get("image_verified")), "duplicate": duplicate,
                        "duplicate_reason": "Image content matches this or an earlier upload." if duplicate else "No matching image fingerprint found.",
                        **semantic})
    return results
