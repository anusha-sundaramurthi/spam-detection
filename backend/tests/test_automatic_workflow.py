"""
Purpose: Protects automatic assessment and ensures the vendor receipt never
leaks private scoring fields.
"""

import asyncio
from unittest.mock import Mock
from bson import ObjectId
from fastapi import BackgroundTasks

from app import main
from app.schemas import AdminFeedbackInput, VendorInput


# Confirms submission is stored first and queues private backend assessment.
def test_vendor_submission_stores_then_queues_assessment_without_scores(monkeypatch):
    """Protect the save-first flow and the score-free vendor receipt."""
    collection = Mock()
    collection.insert_one.return_value = Mock(inserted_id=ObjectId())
    monkeypatch.setattr(main, "submissions", collection)
    assessment_collection = Mock()
    monkeypatch.setattr(main, "assessments", assessment_collection)
    monkeypatch.setattr(main, "upload_records", Mock())
    async def no_uploads(*_args): return {"images": [], "file": None}
    monkeypatch.setattr(main, "store_upload_batch", no_uploads)
    payload = VendorInput(name="Acme", phone="123456789", website=None, portfolio_link="https://example.com/portfolio", address_line1="10 Market Road", address_line2="Suite 2", city="Chennai", state="Tamil Nadu", country="India", pincode="600001",
        service_title="Design service", description="A detailed product design service with research workshops, prototypes, testing, revisions, and handoff documentation for product teams.",
        category="Design", social_links=[], business_registration="REG-123", package_name="Design Sprint",
        package_details="Workshop, prototype, testing, two revisions, and developer handoff files.", price_or_range="$2,000-$3,000",
        special_offer=None)
    tasks = BackgroundTasks()
    receipt = asyncio.run(main.vendor_submit(tasks, payload.model_dump_json(), [], None,
                                             {"sub": "vendor@example.com", "role": "vendor"}))
    stored = collection.insert_one.call_args.args[0]
    assert stored["email"] == "vendor@example.com"
    allowed = (set(VendorInput.model_fields) - {"images", "file"}) | {"vendor_id", "created_at", "updated_at"}
    assert set(stored) == allowed
    assert not ({"status", "assessment_status", "risk_score", "trust_score", "spam_score", "admin_feedback"} & set(stored))
    assert stored["created_at"] == stored["updated_at"] and len(tasks.tasks) == 1
    pending = assessment_collection.insert_one.call_args.args[0]
    assert pending["status"] == "pending" and pending["assessment_status"] == "pending"
    assert set(receipt.model_dump()) == {"id", "status", "created_at", "message"}


# Confirms score arithmetic stores both risk additions and trust reductions for admins.
def test_score_explanation_records_reduction_reasons(monkeypatch):
    payload = VendorInput(name="Acme", phone="9876543210", address_line1="10 Market Road", address_line2="Suite 2",
        city="Chennai", state="Tamil Nadu", country="India", pincode="600001", service_title="Event photography",
        description="Wedding photography with consultation, full-day coverage, editing, and a private client gallery.", category="Photography")
    monkeypatch.setattr(main, "assess_with_local_llm", lambda *_args: {"status":"complete","model":"test","primary_model":"test","backup_model":"backup","fallback_used":False,"attempted_models":["test"],"spam_probability":30,"risk_score":3.0,"trust_score":6.0,"confidence":80,
        "risk_factors":[{"code":"ai_risk_1","label":"Urgency","reason":"Urgency language was detected.","points":3,"max_points":10,"triggered":True}],"trust_factors":[{"code":"ai_trust_1","label":"Details","reason":"Clear deliverables were supplied.","points":6,"max_points":10,"earned":True}],"summary":"Some promotional risk."})
    result = main.assessment_fields(payload, [])
    assert result["score_explanation"]["risk"]["points_added"] == 3.0
    assert result["score_explanation"]["trust"]["points_reduced"] == 4.0
    assert result["spam_score"] == 3.0
    assert result["score_explanation"]["trust"]["reduction_reasons"] == ["Urgency language was detected."]


# Confirms startup recovery retries persisted records that have no AI score.
def test_missing_score_recovery_reassesses_records(monkeypatch):
    first, second = ObjectId(), ObjectId()
    collection = Mock(); collection.distinct.return_value = [first, second]
    retried = []
    monkeypatch.setattr(main, "assessments", collection)
    monkeypatch.setattr(main, "assess_stored_submission", retried.append)
    main.recover_missing_scores()
    assert retried == [first, second]


# Confirms structured false-positive feedback is appended and returned to admins.
def test_admin_feedback_is_stored_as_audit_history(monkeypatch):
    target = ObjectId()
    row = {"_id": target, "name": "Acme", "phone": "123456789", "website": None,
        "service_title": "Design", "description": "Detailed design service", "package_details": "Research and design deliverables",
        "risk_factors": [{"code": "thin_description", "triggered": True}], "trust_factors": [{}],
        "mandatory_services": [{}], "assessment_version": "ai-image-v3", "intelligence": {"model_provenance": {"status": "complete", "model": "qwen3:1.7b", "fallback_used": False}}, "admin_feedback": []}
    collection = Mock(); collection.find_one.return_value = row; collection.find.return_value = [row]
    assessment_collection = Mock(); assessment_collection.find_one.return_value = row
    uploads_collection = Mock(); uploads_collection.find.return_value = []
    monkeypatch.setattr(main, "submissions", collection)
    monkeypatch.setattr(main, "assessments", assessment_collection)
    monkeypatch.setattr(main, "upload_records", uploads_collection)
    result = main.save_feedback(str(target), AdminFeedbackInput(verdict="false_positive", notes="Legitimate concise listing", factor_codes=["thin_description"]), {"sub": "admin@example.com", "role": "admin"})
    pushed = assessment_collection.update_one.call_args.args[1]["$push"]["admin_feedback"]
    assert pushed["verdict"] == "false_positive"
    assert "created_at" in pushed and "updated_at" in pushed
    assert result["feedback_verdict"] == "false_positive"
