"""
Purpose: Protects automatic assessment and ensures the vendor receipt never
leaks private scoring fields.
"""

from unittest.mock import Mock
from bson import ObjectId

from app import main
from app.schemas import VendorInput


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
