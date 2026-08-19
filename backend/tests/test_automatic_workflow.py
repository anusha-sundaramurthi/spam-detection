"""
Purpose: Protects automatic assessment and ensures the vendor receipt never
leaks private scoring fields.
"""

from unittest.mock import Mock
from bson import ObjectId

from app import main
from app.schemas import AdminFeedbackInput, VendorInput


# Confirms submission calculates scores immediately while returning status only.
def test_vendor_submission_scores_automatically_but_receipt_hides_scores(monkeypatch):
    """Protect the central privacy rule: calculate now, disclose only to admins."""
    collection = Mock()
    collection.find.return_value = []
    collection.insert_one.return_value = Mock(inserted_id=ObjectId())
    monkeypatch.setattr(main, "submissions", collection)
    monkeypatch.setattr(main, "assess_with_local_llm", lambda _: {
        "status": "unavailable", "model": "test", "spam_probability": None,
        "trust_score": None, "risk_score": None, "confidence": 0,
        "spam_indicators": ["offline"], "trust_indicators": [], "summary": "fallback"})
    payload = VendorInput(name="Acme", phone="123456789", website=None,
        service_title="Design service", description="A detailed product design service with research workshops, prototypes, testing, revisions, and handoff documentation for product teams.",
        category="Design", social_links=[], business_registration="REG-123", package_name="Design Sprint",
        package_details="Workshop, prototype, testing, two revisions, and developer handoff files.", price_or_range="$2,000-$3,000",
        delivery_timeline="3 weeks", special_offer=None)
    receipt = main.vendor_submit(payload, {"sub": "vendor@example.com", "role": "vendor"})
    stored = collection.insert_one.call_args.args[0]
    assert stored["assessment_status"] == "complete"
    assert stored["email"] == "vendor@example.com"
    assert "risk_factors" in stored and "trust_factors" in stored
    assert set(receipt.model_dump()) == {"id", "status", "created_at", "message"}


# Confirms structured false-positive feedback is appended and returned to admins.
def test_admin_feedback_is_stored_as_audit_history(monkeypatch):
    target = ObjectId()
    row = {"_id": target, "name": "Acme", "phone": "123456789", "website": None,
        "service_title": "Design", "description": "Detailed design service", "package_details": "Research and design deliverables",
        "risk_factors": [{"code": "thin_description", "triggered": True}], "trust_factors": [{}],
        "mandatory_services": [{}], "intelligence": {"disagreement": {"level": "low"}}, "admin_feedback": []}
    collection = Mock(); collection.find_one.return_value = row; collection.find.return_value = [row]
    monkeypatch.setattr(main, "submissions", collection)
    result = main.save_feedback(str(target), AdminFeedbackInput(verdict="false_positive", notes="Legitimate concise listing", factor_codes=["thin_description"]), {"sub": "admin@example.com", "role": "admin"})
    pushed = collection.update_one.call_args.args[1]["$push"]["admin_feedback"]
    assert pushed["verdict"] == "false_positive"
    assert result["feedback_verdict"] == "false_positive"
