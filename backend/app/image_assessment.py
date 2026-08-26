# image_assessment.py
"""
Purpose: Assesses each stored service image with a real local Ollama vision model
(Qwen2.5-VL primary, Moondream fallback) and combines semantic relevance/spam
findings, a per-image trust/risk score, and deterministic duplicate checks.
"""

import base64
import os
from typing import Literal
import pymupdf as fitz  # PyMuPDF -- already a dependency, reused here to downscale images
import httpx
from pydantic import BaseModel, Field, ValidationError

from .llm_scoring import OLLAMA_LOCK
from .uploads import resolve_upload

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")
VISION_BACKUP_MODEL = os.getenv("OLLAMA_VISION_BACKUP_MODEL", "moondream:1.8b")

# FIX: this was missing at module level, causing a NameError crash inside
# attempt_vision_model every time a vision call was made.
VISION_TIMEOUT = float(os.getenv("VISION_TIMEOUT_SECONDS", "1000"))

# FIX: vision token count scales with pixel count. A full-resolution phone
# photo (e.g. 3000x4000) can push qwen2.5vl's request over its context size
# on its own -- that's what caused the 400 "exceeds context size" failures
# and the fallback to the weaker moondream model. Downscaling to a max
# dimension before sending cuts tokens and CPU inference time drastically
# with no real loss for a "what's in this image" classification task.
# Lowered from 768 -> 640: still comfortably legible for spot-checking a
# business name/phone/watermark printed in a service photo (the thing the
# spam/identity check actually depends on), while meaningfully cutting
# vision-token count, base64 payload size, and stored-copy size versus 768.
MAX_IMAGE_DIMENSION = 640


# FIX: PyMuPDF needs an explicit, correct filetype hint to open a raw raster
# image stream (jpg/png/webp/...) with no filename attached. "img" is not a
# real filetype and both "img" and None caused every call to fail with
# FileDataError ("Failed to open stream"). Sniff the format from the file's
# magic bytes instead so the right hint is always passed.
def _guess_image_filetype(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if image_bytes.startswith(b"BM"):
        return "bmp"
    return "jpg"  # best-effort fallback for an unrecognized/uncommon format


# Downscales raster image bytes so neither side exceeds MAX_IMAGE_DIMENSION.
# Uses PyMuPDF (already a dependency) rather than adding Pillow.
def downscale_image(image_bytes: bytes) -> bytes:
    try:
        filetype = _guess_image_filetype(image_bytes)
        doc = fitz.open(stream=image_bytes, filetype=filetype)
        page = doc[0]
        longest_side = max(page.rect.width, page.rect.height)
        if longest_side <= MAX_IMAGE_DIMENSION:
            doc.close()
            return image_bytes
        scale = MAX_IMAGE_DIMENSION / longest_side
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        # jpg_quality=82 (PyMuPDF default is 95): visibly lossless for this
        # use case (relevance/spam/text-legibility check, not print output)
        # and noticeably cuts encoded size -> smaller base64 payload sent to
        # Ollama and less storage if the downscaled copy is ever persisted.
        resized = pix.tobytes("jpg", jpg_quality=82)
        doc.close()
        return resized
    except Exception as exc:
        print(f"[IMAGE DOWNSCALE FAILURE] {type(exc).__name__}: {exc}")
        return image_bytes


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
    try:
        with OLLAMA_LOCK:
            response = httpx.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", timeout=VISION_TIMEOUT, json={
                "model": model, "stream": False, "format": VisionResult.model_json_schema(),
                # num_ctx trimmed from 4096 -> 3072: context here was already
                # capped to IMAGE_CONTEXT_FIELDS, and MAX_IMAGE_DIMENSION is
                # now 640 (was 768), so fewer vision tokens are produced.
                # Kept above document_assessment's 2048 since image token
                # count is less predictable than fixed-length text.
                "options": {"temperature": 0, "num_predict": 260, "num_ctx": 3072},
                "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
            })
        response.raise_for_status()
        parsed = VisionResult.model_validate_json(response.json()["message"]["content"])
        # FIX: a degraded local vision model can return a structurally valid
        # but degenerate confidence=0 result. Treat it as a failed attempt so
        # the pipeline retries with the next model instead of silently
        # accepting an unreliable score as "Complete".
        if parsed.confidence == 0:
            raise ValueError("degenerate zero-confidence result")
        return parsed.model_dump(), None
    except (OSError, httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
        print(f"[VISION MODEL FAILURE] {model}: {type(exc).__name__}: {exc}")
        return None, f"{model}: {type(exc).__name__}"


# Uses the configured vision model to inspect actual pixels for relevance, visual
# spam, a short description, and a trust/risk score with an explicit reason.
# Tries the primary (Qwen2.5-VL) first, falling back to Moondream only if it fails.
def assess_image_semantics(image: dict, vendor_context: dict) -> dict:
    """Return a validated visual classification or an explicit unavailable state."""
    try:
        raw_bytes = resolve_upload(image["storage_name"]).read_bytes()
        encoded = base64.b64encode(downscale_image(raw_bytes)).decode("ascii")
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
    return results