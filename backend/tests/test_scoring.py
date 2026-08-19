"""
Purpose: Exercises trusted, obvious-spam, and duplicate vendor scenarios against
the deterministic 10-point factor ledgers.
"""

from app.schemas import VendorInput
from app.scoring import score_vendor


# Builds a valid trusted vendor fixture with optional field overrides.
def vendor(**overrides):
    values = dict(name="Acme Studio", email="hello@acme.test", phone="+1 555 123 4567", website="https://acme.test",
        service_title="Product design", category="Design", social_links=["https://linkedin.com/company/acme"], business_registration="REG-12345",
        description="We provide research, interface design, prototyping, testing, and accessibility reviews for established product teams across several industries.",
        package_name="Design Sprint", package_details="Research, prototype, testing, two revisions, and handoff files.", price_or_range="$2,000-$3,000", delivery_timeline="3 weeks", special_offer=None)
    values.update(overrides)
    return VendorInput(**values)


# Confirms a transparent, verifiable vendor earns a strong trust score.
def test_trusted_vendor_scores_well():
    result = score_vendor(vendor(), [])
    assert result["trust_score"] >= 7
    assert result["risk_level"] == "low"


# Confirms suspicious URLs and description-first spam copy score high risk.
def test_spam_vendor_is_high_risk():
    result = score_vendor(vendor(email="x@mailinator.com", website="https://bit.ly/free-money", description="ACT NOW 100% FREE CLICK HERE 🚀🚀🚀🚀🚀🚀"), [])
    assert result["risk_score"] >= 6.5
    assert result["risk_level"] == "high"


# Confirms exact duplicate description points include the matching submission reference.
def test_duplicate_is_explained():
    submitted = vendor()
    result = score_vendor(submitted, [{"id": 7, "email": "other@example.test", "phone": "0", "description": submitted.description}])
    rule = next(r for r in result["risk_factors"] if r["code"] == "duplicate_submission")
    assert rule["triggered"] and "#7" in rule["reason"]


# Confirms absent optional website and profiles never add spam-risk points.
def test_optional_online_profiles_do_not_create_risk():
    result = score_vendor(vendor(website=None, social_links=[]), [])
    assert next(r for r in result["risk_factors"] if r["code"] == "invalid_url")["points"] == 0
    assert all(r["code"] not in {"invalid_email", "disposable_email"} for r in result["risk_factors"])
