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
