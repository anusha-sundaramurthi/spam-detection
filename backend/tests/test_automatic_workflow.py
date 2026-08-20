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
    monkeypatch.setattr(main, "assess_with_local_llm", lambda _data, _evidence: {
        "status": "complete", "model": "llama3.2:3b", "primary_model": "llama3.2:3b", "backup_model": "qwen2.5:3b",
        "fallback_used": False, "attempted_models": ["llama3.2:3b"], "spam_probability": 20,
        "trust_score": 8, "risk_score": 2, "confidence": 80,
        "risk_factors": [{"code":"ai_risk_1","label":"Low risk","reason":"Specific service details","points":2,"max_points":10,"triggered":True}],
        "trust_factors": [{"code":"ai_trust_1","label":"Detailed offer","reason":"Clear deliverables","points":8,"max_points":10,"earned":True}],
        "spam_indicators": [], "trust_indicators": ["Clear deliverables"], "summary": "Low spam risk."})
    payload = VendorInput(name="Acme", phone="123456789", website=None, portfolio_link="https://example.com/portfolio", address_line1="10 Market Road", address_line2="Suite 2", city="Chennai", state="Tamil Nadu", country="India", pincode="600001",
        service_title="Design service", description="A detailed product design service with research workshops, prototypes, testing, revisions, and handoff documentation for product teams.",
        category="Design", social_links=[], business_registration="REG-123", package_name="Design Sprint",
        package_details="Workshop, prototype, testing, two revisions, and developer handoff files.", price_or_range="$2,000-$3,000",
        special_offer=None)
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
        "mandatory_services": [{}], "assessment_version": "ai-only-v1", "intelligence": {"model_provenance": {"status": "complete", "model": "llama3.2:3b", "fallback_used": False}}, "admin_feedback": []}
    collection = Mock(); collection.find_one.return_value = row; collection.find.return_value = [row]
    monkeypatch.setattr(main, "submissions", collection)
    result = main.save_feedback(str(target), AdminFeedbackInput(verdict="false_positive", notes="Legitimate concise listing", factor_codes=["thin_description"]), {"sub": "admin@example.com", "role": "admin"})
    pushed = collection.update_one.call_args.args[1]["$push"]["admin_feedback"]
    assert pushed["verdict"] == "false_positive"
    assert result["feedback_verdict"] == "false_positive"
