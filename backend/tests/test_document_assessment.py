"""
Purpose: Verifies document text extraction, deterministic Aadhaar/name
verification, and AI judgment produce persisted-ready results without
fabricating scores when no text could ever be extracted.
"""

from pathlib import Path

from app import document_assessment


# Confirms a document with directly extractable text is judged normally and
# deterministic Aadhaar/name evidence is computed from that same text.
def test_extractable_text_document_is_judged_with_matching_evidence(monkeypatch):
    monkeypatch.setattr(document_assessment, "resolve_upload", lambda _name: Path("/fake/doc.pdf"))
    monkeypatch.setattr(document_assessment, "extract_document_text",
        lambda _path, _content_type: ("Name: Acme Events\nAadhaar: 1234 5678 9012\nRegistered proof.", None))
    monkeypatch.setattr(document_assessment, "judge_document", lambda _text, _context, _evidence: {
        "status": "complete", "model": "doc-test", "primary_model": "doc-test", "backup_model": "backup",
        "fallback_used": False, "relevance": "relevant", "spam_detected": False, "trust_score": 8.0,
        "risk_score": 1.0, "confidence": 90, "extracted_summary": "Business registration proof.",
        "relevance_reason": "Matches declared business.", "spam_reason": "No spam indicators.",
        "score_reason": "Aadhaar and name both matched.",
    })
    file_record = {"storage_name": "doc.pdf", "original_name": "doc.pdf", "content_type": "application/pdf"}
    result = document_assessment.assess_submission_document(file_record, {"name": "Acme Events"}, "123456789012")
    assert result["status"] == "complete"
    assert result["aadhaar_verification"]["match"] is True
    assert result["name_verification"]["found_in_document"] is True
    assert result["trust_score"] == 8.0 and result["risk_score"] == 1.0


# Confirms a declared Aadhaar number that does not match the document text is
# reported as a mismatch rather than silently ignored.
def test_aadhaar_mismatch_is_recorded_not_hidden(monkeypatch):
    monkeypatch.setattr(document_assessment, "resolve_upload", lambda _name: Path("/fake/doc.pdf"))
    monkeypatch.setattr(document_assessment, "extract_document_text",
        lambda _path, _content_type: ("Name: Acme Events\nAadhaar: 1111 2222 3333", None))
    monkeypatch.setattr(document_assessment, "judge_document", lambda *_args: {
        "status": "complete", "model": "doc-test", "primary_model": "doc-test", "backup_model": "backup",
        "fallback_used": False, "relevance": "relevant", "spam_detected": False, "trust_score": 5.0,
        "risk_score": 3.0, "confidence": 80, "extracted_summary": "Proof supplied.",
        "relevance_reason": "Business proof.", "spam_reason": "None found.",
        "score_reason": "Mismatched ID reduces trust.",
    })
    file_record = {"storage_name": "doc.pdf", "original_name": "doc.pdf", "content_type": "application/pdf"}
    result = document_assessment.assess_submission_document(file_record, {"name": "Acme Events"}, "999988887777")
    assert result["aadhaar_verification"]["declared_present"] is True
    assert result["aadhaar_verification"]["found_in_document"] is True
    assert result["aadhaar_verification"]["match"] is False


# Confirms a vendor name that never appears in the document text is flagged,
# not assumed to match.
def test_name_not_found_in_document_is_flagged(monkeypatch):
    monkeypatch.setattr(document_assessment, "resolve_upload", lambda _name: Path("/fake/doc.pdf"))
    monkeypatch.setattr(document_assessment, "extract_document_text",
        lambda _path, _content_type: ("Registration certificate for Different Business Pvt Ltd.", None))
    monkeypatch.setattr(document_assessment, "judge_document", lambda *_args: {
        "status": "complete", "model": "doc-test", "primary_model": "doc-test", "backup_model": "backup",
        "fallback_used": False, "relevance": "irrelevant", "spam_detected": False, "trust_score": 2.0,
        "risk_score": 6.0, "confidence": 75, "extracted_summary": "Certificate for a different business.",
        "relevance_reason": "Name does not match declared vendor.", "spam_reason": "None found.",
        "score_reason": "Business identity mismatch.",
    })
    file_record = {"storage_name": "doc.pdf", "original_name": "doc.pdf", "content_type": "application/pdf"}
    result = document_assessment.assess_submission_document(file_record, {"name": "Acme Events"}, None)
    assert result["name_verification"]["declared_present"] is True
    assert result["name_verification"]["found_in_document"] is False


# Confirms a scanned PDF (no direct text) falls back to the vision reader and
# that extracted text is used for both Aadhaar detection and judgment.
def test_scanned_document_falls_back_to_vision_read(monkeypatch):
    monkeypatch.setattr(document_assessment, "resolve_upload", lambda _name: Path("/fake/scan.pdf"))
    monkeypatch.setattr(document_assessment, "extract_document_text",
        lambda _path, _content_type: ("", b"fake-page-image-bytes"))
    monkeypatch.setattr(document_assessment, "describe_scanned_document", lambda _image_bytes, _context: {
        "status": "complete", "model": "moondream:1.8b", "fallback_used": True,
        "text": "Name: Acme Events\nAadhaar: 1234 5678 9012",
    })
    monkeypatch.setattr(document_assessment, "judge_document", lambda text, _context, _evidence: {
        "status": "complete", "model": "doc-test", "primary_model": "doc-test", "backup_model": "backup",
        "fallback_used": False, "relevance": "relevant", "spam_detected": False, "trust_score": 7.0,
        "risk_score": 1.5, "confidence": 70, "extracted_summary": "Read from scanned page.",
        "relevance_reason": "Matches vendor.", "spam_reason": "None found.", "score_reason": "Consistent evidence.",
    } if "Acme" in text else None)
    file_record = {"storage_name": "scan.pdf", "original_name": "scan.pdf", "content_type": "application/pdf"}
    result = document_assessment.assess_submission_document(file_record, {"name": "Acme Events"}, "123456789012")
    assert result["status"] == "complete"
    assert result["aadhaar_verification"]["extracted_via_fallback_model"] is True
    assert result["aadhaar_verification"]["match"] is True


# Confirms scanned documents use the dedicated vision model settings and do
# not accidentally send images to the text-only document judgment models.
def test_scanned_document_reader_uses_only_vision_models(monkeypatch):
    monkeypatch.setattr(document_assessment, "DOC_VISION_MODEL", "primary-vision-model")
    monkeypatch.setattr(document_assessment, "DOC_VISION_BACKUP_MODEL", "backup-vision-model")
    attempted_models = []

    def attempt(_encoded, _prompt, model):
        attempted_models.append(model)
        if model == "primary-vision-model":
            return None, "primary unavailable"
        return "Visible registration document text", None

    monkeypatch.setattr(document_assessment, "attempt_scan_read", attempt)
    result = document_assessment.describe_scanned_document(b"fake-image", {"name": "Acme Events"})
    assert attempted_models == ["primary-vision-model", "backup-vision-model"]
    assert result["status"] == "complete" and result["fallback_used"] is True


# Confirms a legacy .doc file (no text extractor, no page image) is reported
# as unavailable instead of being judged on empty text and returning a
# fabricated-looking "complete" score.
def test_doc_with_no_extractable_text_is_unavailable_not_fabricated(monkeypatch):
    monkeypatch.setattr(document_assessment, "resolve_upload", lambda _name: Path("/fake/legacy.doc"))
    monkeypatch.setattr(document_assessment, "extract_document_text", lambda _path, _content_type: ("", None))
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("judge_document must not be called with no extractable text")
    monkeypatch.setattr(document_assessment, "judge_document", fail_if_called)
    file_record = {"storage_name": "legacy.doc", "original_name": "legacy.doc", "content_type": "application/msword"}
    result = document_assessment.assess_submission_document(file_record, {"name": "Acme Events"}, "123456789012")
    assert result["status"] == "unavailable"
    assert result["trust_score"] is None and result["risk_score"] is None
    assert result["relevance"] == "unavailable"


# Confirms judge_document automatically retries with the backup model when the
# primary model fails, mirroring the vision assessment fallback pattern.
def test_judge_document_falls_back_to_backup_model(monkeypatch):
    monkeypatch.setattr(document_assessment, "DOC_TEXT_MODEL", "primary-doc-model")
    monkeypatch.setattr(document_assessment, "DOC_TEXT_BACKUP_MODEL", "backup-doc-model")
    def attempt(_prompt, _system_prompt, model):
        if model == "primary-doc-model":
            return None, "primary-doc-model: TimeoutError"
        return {"relevance": "relevant", "spam_detected": False, "trust_score": 6.0, "risk_score": 2.0,
                "confidence": 65, "extracted_summary": "Backup model read.",
                "relevance_reason": "Matches vendor.", "spam_reason": "None found.",
                "score_reason": "Consistent with declared identity."}, None
    monkeypatch.setattr(document_assessment, "attempt_document_judgment", attempt)
    result = document_assessment.judge_document("some document text", {"name": "Acme"}, {})
    assert result["status"] == "complete"
    assert result["model"] == "backup-doc-model"
    assert result["fallback_used"] is True


# Confirms both models failing is reported explicitly rather than defaulting
# to a misleading "complete" or zero score.
def test_judge_document_both_models_failing_is_explicit(monkeypatch):
    monkeypatch.setattr(document_assessment, "DOC_TEXT_MODEL", "primary-doc-model")
    monkeypatch.setattr(document_assessment, "DOC_TEXT_BACKUP_MODEL", "backup-doc-model")
    monkeypatch.setattr(document_assessment, "attempt_document_judgment",
        lambda _prompt, _system_prompt, model: (None, f"{model}: HTTPError"))
    result = document_assessment.judge_document("some document text", {"name": "Acme"}, {})
    assert result["status"] == "unavailable"
    assert result["trust_score"] is None and result["risk_score"] is None
    assert "primary-doc-model" in result["spam_reason"] and "backup-doc-model" in result["spam_reason"]


# Confirms a submission with no supporting file at all skips document
# assessment cleanly instead of raising.
def test_no_file_record_returns_none():
    assert document_assessment.assess_submission_document(None, {"name": "Acme"}, None) is None