"""
Purpose: Validates and stores optional demo service images and one supporting
document outside MongoDB while returning safe metadata for submission records.
"""

import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads")).resolve()
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
FILE_TYPES = {"application/pdf": ".pdf", "application/msword": ".doc",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}
MAX_IMAGES, MAX_IMAGE_BYTES, MAX_FILE_BYTES = 5, 5 * 1024 * 1024, 10 * 1024 * 1024


# Reads a bounded upload and rejects content that exceeds its configured limit.
async def bounded_content(upload: UploadFile, limit: int) -> bytes:
    """Prevent oversized uploads from consuming unbounded memory or disk space."""
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"{upload.filename} exceeds the upload size limit")
    return content


# Stores one validated upload under a randomized server-controlled filename.
async def store_upload(upload: UploadFile, allowed: dict[str, str], limit: int, kind: str, owner: str) -> dict:
    """Ignore client paths and persist only approved media types with safe metadata."""
    if upload.content_type not in allowed:
        raise HTTPException(415, f"Unsupported {kind} type for {upload.filename}")
    content = await bounded_content(upload, limit)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid4().hex}{allowed[upload.content_type]}"
    target = (UPLOAD_ROOT / storage_name).resolve()
    if target.parent != UPLOAD_ROOT:
        raise HTTPException(400, "Unsafe upload path")
    target.write_bytes(content)
    return {"storage_name": storage_name, "original_name": Path(upload.filename or kind).name,
            "content_type": upload.content_type, "size": len(content), "kind": kind, "owner": owner}


# Validates and stores the complete optional upload batch for one vendor.
async def store_upload_batch(images: list[UploadFile], attachment: UploadFile | None, owner: str) -> dict:
    """Apply image-count, media-type, and size limits before returning MongoDB metadata."""
    if len(images) > MAX_IMAGES:
        raise HTTPException(413, f"A maximum of {MAX_IMAGES} service images is allowed")
    stored_images = [await store_upload(image, IMAGE_TYPES, MAX_IMAGE_BYTES, "image", owner) for image in images]
    stored_file = await store_upload(attachment, FILE_TYPES, MAX_FILE_BYTES, "file", owner) if attachment else None
    return {"images": stored_images, "file": stored_file}


# Resolves an already-generated upload filename without allowing traversal.
def resolve_upload(storage_name: str) -> Path:
    """Return a safe existing upload path or a not-found response."""
    target = (UPLOAD_ROOT / Path(storage_name).name).resolve()
    if target.parent != UPLOAD_ROOT or not target.is_file():
        raise HTTPException(404, "Upload not found")
    return target
