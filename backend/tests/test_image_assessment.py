"""
Purpose: Verifies that every image receives persisted-ready semantic, integrity,
and duplicate assessment fields without fabricating unavailable vision output.
"""

from app import image_assessment


# Confirms duplicate hashes are deterministic while semantic findings remain per image.
def test_each_image_gets_duplicate_and_semantic_results(monkeypatch):
    monkeypatch.setattr(image_assessment, "assess_image_semantics", lambda _image, _context: {
        "status": "complete", "model": "vision-test", "relevance": "relevant", "spam_detected": False,
        "confidence": 90, "detected_content": "Wedding stage", "relevance_reason": "Matches event service.",
        "spam_reason": "No visual spam found.",
    })
    images = [{"storage_name": "one.jpg", "original_name": "one.jpg", "sha256": "abc", "image_verified": True},
              {"storage_name": "two.jpg", "original_name": "two.jpg", "sha256": "abc", "image_verified": True}]
    results = image_assessment.assess_submission_images(images, {"category": "Photography"}, set())
    assert len(results) == 2 and not results[0]["duplicate"] and results[1]["duplicate"]
    assert all(item["relevance"] == "relevant" and item["spam_detected"] is False for item in results)


# Confirms unavailable vision is explicit rather than misclassified as safe.
def test_unavailable_vision_is_not_reported_as_clean(monkeypatch):
    monkeypatch.setattr(image_assessment, "assess_image_semantics", lambda _image, _context: {
        "status": "unavailable", "model": "missing", "relevance": "unavailable", "spam_detected": None,
        "confidence": 0, "detected_content": "Not assessed", "relevance_reason": "Unavailable.", "spam_reason": "Model missing.",
    })
    result = image_assessment.assess_submission_images(
        [{"storage_name": "one.jpg", "original_name": "one.jpg", "sha256": "abc", "image_verified": True}], {}, set())[0]
    assert result["status"] == "unavailable" and result["spam_detected"] is None


# Confirms image assessment uses the dedicated vision model configuration and
# retries its vision backup without ever falling through to a text model.
def test_image_semantics_uses_only_vision_models(monkeypatch, tmp_path):
    monkeypatch.setattr(image_assessment, "VISION_MODEL", "primary-vision-model")
    monkeypatch.setattr(image_assessment, "VISION_BACKUP_MODEL", "backup-vision-model")
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake-image")
    monkeypatch.setattr(image_assessment, "resolve_upload", lambda _name: image_path)
    attempted_models = []

    def attempt(_encoded, _prompt, model):
        attempted_models.append(model)
        if model == "primary-vision-model":
            return None, "primary unavailable"
        return {"relevance": "relevant", "spam_detected": False, "confidence": 80,
                "detected_content": "Wedding photography", "relevance_reason": "Matches category.",
                "spam_reason": "No visual spam."}, None

    monkeypatch.setattr(image_assessment, "attempt_vision_model", attempt)
    result = image_assessment.assess_image_semantics(
        {"storage_name": "photo.jpg"}, {"category": "Photography"})
    assert attempted_models == ["primary-vision-model", "backup-vision-model"]
    assert result["status"] == "complete" and result["fallback_used"] is True
