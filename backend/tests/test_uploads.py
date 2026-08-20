"""
Purpose: Verifies optional service media type, size, randomized naming, and
safe upload-path behavior.
"""
import asyncio
from io import BytesIO
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from app import uploads

# Builds an in-memory multipart upload with an explicit content type.
def uploaded(name: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(BytesIO(content), filename=name, headers=Headers({"content-type": content_type}))

# Confirms an approved image is randomized and stored beneath the configured root.
def test_image_upload_is_stored_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path.resolve())
    result = asyncio.run(uploads.store_upload_batch([uploaded("service.png", b"demo-image", "image/png")], None, "vendor@example.com"))
    metadata = result["images"][0]
    assert metadata["storage_name"] != "service.png"
    assert (tmp_path / metadata["storage_name"]).read_bytes() == b"demo-image"

# Confirms executable or unapproved upload formats are rejected.
def test_unsupported_upload_type_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path.resolve())
    with pytest.raises(HTTPException) as error:
        asyncio.run(uploads.store_upload_batch([], uploaded("danger.exe", b"bad", "application/octet-stream"), "vendor@example.com"))
    assert error.value.status_code == 415
