# image_assessment.py
"""
Purpose: Assesses each stored service image with the configured local Ollama
vision model and combines relevance/spam scores with deterministic duplicates.
"""

import base64
import logging
import os
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .llm_scoring import OLLAMA_LOCK
from .logging_config import log_event
from .uploads import resolve_upload

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream:1.8b")
VISION_BACKUP_MODEL = os.getenv("OLLAMA_VISION_BACKUP_MODEL", "moondream:1.8b")
VISION_TIMEOUT = float(os.getenv("VISION_TIMEOUT_SECONDS", "1000"))
logger = logging.getLogger("vendor_trust.vision")

# Fields from the vendor form an image should be checked against — identity
# fields too (name/email/phone/city), not just the service description, since
# a spam image can carry a different business name/phone than the form.
IMAGE_CONTEXT_FIELDS = ("name", "email", "phone", "city", "category", "service_title",
                        "description", "package_name", "package_details", "special_offer")


class VisionResult(BaseModel):
    relevance: Literal["relevant", "irrelevant"]
    spam_detected: bool
    trust_score: float = Field(ge=0, le=10)
    risk_score: float = Field(ge=0, le=10)
    confidence: int = Field(ge=0, le=100)
    detected_content: str = Field(min_length=2, max_length=240)
    relevance_reason: str = Field(min_length=3, max_length=240)
    spam_reason: str = Field(min_length=3, max_length=240)
    score_reason: str = Field(min_length=3, max_length=240)


# Calls and validates one configured vision model without applying fallback policy.
def attempt_vision_model(encoded: str, prompt: str, model: str) -> tuple[dict | None, str | None]:
    """Return one valid image classification or a concise failure reason."""
    started = perf_counter()
    log_event(logger, "vision_model_attempt_started", model=model, timeout_seconds=VISION_TIMEOUT)
    try:
        with OLLAMA_LOCK:
            response = httpx.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", timeout=VISION_TIMEOUT, json={
                "model": model, "stream": False, "format": VisionResult.model_json_schema(),
                "options": {"temperature": 0, "num_predict": 260},
                "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
            })
        response.raise_for_status()
        parsed = VisionResult.model_validate_json(response.json()["message"]["content"])
        log_event(logger, "vision_model_attempt_completed", model=model,
                  duration_ms=round((perf_counter() - started) * 1000, 1),
                  relevance=parsed.relevance, spam_detected=parsed.spam_detected,
                  trust_score=parsed.trust_score, risk_score=parsed.risk_score, confidence=parsed.confidence)
        return parsed.model_dump(), None
    except (OSError, httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
        log_event(logger, "vision_model_attempt_failed", level=logging.WARNING, model=model,
                  duration_ms=round((perf_counter() - started) * 1000, 1), error_type=type(exc).__name__)
        return None, f"{model}: {type(exc).__name__}"


# Uses the configured vision model to inspect actual pixels for relevance, visual
# spam, a short description, and a trust/risk score with an explicit reason.
# Tries each distinct configured vision model without ever using a text-only model.
def assess_image_semantics(image: dict, vendor_context: dict) -> dict:
    """Return a validated visual classification or an explicit unavailable state."""
    try:
        encoded = base64.b64encode(resolve_upload(image["storage_name"]).read_bytes()).decode("ascii")
    except OSError as exc:
        return {"status": "unavailable", "model": None, "relevance": "unavailable", "spam_detected": None,
                "trust_score": None, "risk_score": None, "confidence": 0, "detected_content": "Not assessed",
                "relevance_reason": "Image file unreadable.", "spam_reason": f"{type(exc).__name__}",
                "score_reason": "Image could not be read."}

    context = {key: vendor_context.get(key) for key in IMAGE_CONTEXT_FIELDS}
    prompt = (
        "Inspect this vendor service image. Describe what is visibly in it in one or two sentences. "
        "Decide whether its visible content is relevant to the submitted event service and consistent "
        "with the vendor's declared identity (name, email, phone, city) — flag it if any text visible in "
        "the image (business name, phone number, watermark, contact details) contradicts the declared "
        "vendor context below. Detect visual spam including unrelated advertising, QR/payment diversion, "
        "excessive promotional text, fake guarantees, contact diversion, scams, or misleading offers. "
        "Then give this image a trust_score (0-10, how much this image supports the vendor's legitimacy) "
        "and a risk_score (0-10, how much this image raises spam/fraud concern), each backed by a specific "
        "score_reason. Do not infer facts that are not visible. Vendor context: " + str(context))

    failures = []
    for index, model in enumerate(dict.fromkeys([VISION_MODEL, VISION_BACKUP_MODEL])):
        result, failure = attempt_vision_model(encoded, prompt, model)
        if result:
            return {"status": "complete", "model": model, "primary_model": VISION_MODEL,
                     "backup_model": VISION_BACKUP_MODEL, "fallback_used": index > 0, **result}
        failures.append(failure)

    return {"status": "unavailable", "model": None, "primary_model": VISION_MODEL, "backup_model": VISION_BACKUP_MODEL,
            "fallback_used": False, "relevance": "unavailable", "spam_detected": None, "trust_score": None,
            "risk_score": None, "confidence": 0, "detected_content": "Not assessed",
            "relevance_reason": "Local vision assessment unavailable.", "spam_reason": "; ".join(failures),
            "score_reason": "No score: local vision assessment unavailable."}


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
    log_event(logger, "image_batch_assessment_completed", image_count=len(results),
              complete_count=sum(item.get("status") == "complete" for item in results),
              spam_count=sum(item.get("spam_detected") is True for item in results),
              duplicate_count=sum(bool(item.get("duplicate")) for item in results))
    return results
