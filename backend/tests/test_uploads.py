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
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (200).to_bytes(4, "big") + (150).to_bytes(4, "big") + b"demo-image"
    result = asyncio.run(uploads.store_upload_batch([uploaded("service.png", content, "image/png")], None, "vendor@example.com"))
    metadata = result["images"][0]
    assert metadata["storage_name"] != "service.png"
    assert metadata["image_verified"] and metadata["width"] == 200 and metadata["height"] == 150
    assert (tmp_path / metadata["storage_name"]).read_bytes() == content

# Confirms a MIME label cannot disguise arbitrary bytes as a service image.
def test_fake_image_bytes_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path.resolve())
    with pytest.raises(HTTPException) as error:
        asyncio.run(uploads.store_upload_batch([uploaded("fake.png", b"not-an-image", "image/png")], None, "vendor@example.com"))
    assert error.value.status_code == 400

# Confirms executable or unapproved upload formats are rejected.
def test_unsupported_upload_type_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path.resolve())
    with pytest.raises(HTTPException) as error:
        asyncio.run(uploads.store_upload_batch([], uploaded("danger.exe", b"bad", "application/octet-stream"), "vendor@example.com"))
    assert error.value.status_code == 415
