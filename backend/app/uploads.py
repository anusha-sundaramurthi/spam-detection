"""
Purpose: Validates and stores optional demo service images and one supporting
document outside MongoDB while returning safe metadata for submission records.
"""

import os
from pathlib import Path
from hashlib import sha256
import struct
from uuid import uuid4

from fastapi import HTTPException, UploadFile

UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads")).resolve()
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
FILE_TYPES = {"application/pdf": ".pdf", "application/msword": ".doc",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}
MAX_IMAGES, MAX_IMAGE_BYTES, MAX_FILE_BYTES = 5, 5 * 1024 * 1024, 10 * 1024 * 1024


# Reads trusted dimensions from supported image headers and rejects mislabeled bytes.
def verified_image_metadata(content: bytes, content_type: str) -> tuple[str, int, int]:
    """Verify PNG, JPEG, or WebP signatures and dimensions without external native tools."""
    if content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24:
        width, height = struct.unpack(">II", content[16:24]); return "png", width, height
    if content_type == "image/webp" and len(content) >= 30 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        chunk = content[12:16]
        if chunk == b"VP8X":
            return "webp", 1 + int.from_bytes(content[24:27], "little"), 1 + int.from_bytes(content[27:30], "little")
        if chunk == b"VP8L" and content[20] == 0x2F:
            bits = int.from_bytes(content[21:25], "little"); return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if content_type == "image/jpeg" and content.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(content):
            if content[offset] != 0xFF:
                offset += 1; continue
            marker = content[offset + 1]; offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(content): break
            length = int.from_bytes(content[offset:offset + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and offset + 7 < len(content):
                return "jpeg", int.from_bytes(content[offset + 5:offset + 7], "big"), int.from_bytes(content[offset + 3:offset + 5], "big")
            if length < 2: break
            offset += length
    raise HTTPException(400, "Image bytes do not match a supported readable image format")


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
    image_details = {}
    if kind == "image":
        detected_format, width, height = verified_image_metadata(content, upload.content_type)
        if width < 100 or height < 100:
            raise HTTPException(400, f"{upload.filename} is too small to verify as a service image")
        image_details = {"width": width, "height": height, "detected_format": detected_format,
                         "image_verified": True, "sha256": sha256(content).hexdigest()}
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid4().hex}{allowed[upload.content_type]}"
    target = (UPLOAD_ROOT / storage_name).resolve()
    if target.parent != UPLOAD_ROOT:
        raise HTTPException(400, "Unsafe upload path")
    target.write_bytes(content)
    return {"storage_name": storage_name, "original_name": Path(upload.filename or kind).name,
            "content_type": upload.content_type, "size": len(content), "kind": kind, "owner": owner,
            **image_details}


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
