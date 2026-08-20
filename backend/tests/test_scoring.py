"""
Purpose: Verifies deterministic checks remain useful evidence while contributing
zero points and never producing final trust or risk scores.
"""
from app.schemas import VendorInput
from app.scoring import analyze_vendor

# Builds a complete vendor fixture for evidence-only analysis.
def vendor(**overrides):
    values=dict(name="Acme Studio",email="hello@acme.test",phone="+1 555 123 4567",website="https://acme.test",portfolio_link="https://acme.test/portfolio",address_line1="10 Market Road",address_line2="Suite 2",city="Chennai",state="Tamil Nadu",country="India",pincode="600001",service_title="Product design",category="Design",social_links=["https://linkedin.com/company/acme"],business_registration="REG-12345",description="We provide research, interface design, prototyping, testing, and accessibility reviews for established product teams across several industries.",package_name="Design Sprint",package_details="Research, prototype, testing, two revisions, and handoff files.",price_or_range="$2,000-$3,000",special_offer=None)
    values.update(overrides);return VendorInput(**values)

# Confirms every deterministic finding has explicit zero scoring weight.
def test_deterministic_analysis_never_scores():
    result=analyze_vendor(vendor(description="ACT NOW 100% FREE CLICK HERE"),[])
    assert result["mode"]=="evidence_only" and result["scoring_weight"]==0
    assert all(item["points"]==0 and item["scoring_weight"]==0 for item in result["risk_evidence"]+result["trust_evidence"])
    assert "risk_score" not in result and "trust_score" not in result

# Confirms suspicious content and exact duplicates remain visible to the AI and admin.
def test_spam_and_duplicate_evidence_is_explained():
    submitted=vendor(description="ACT NOW and click here for guaranteed results")
    result=analyze_vendor(submitted,[{"id":7,"description":submitted.description}])
    risks={item["code"]:item for item in result["risk_evidence"]}
    assert risks["spam_keywords"]["triggered"]
    assert risks["duplicate_submission"]["triggered"] and "#7" in risks["duplicate_submission"]["reason"]

# Confirms missing optional website and profiles remain neutral evidence.
def test_optional_profiles_are_not_flagged():
    result=analyze_vendor(vendor(website=None,social_links=[]),[])
    invalid=next(item for item in result["risk_evidence"] if item["code"]=="invalid_url")
    assert not invalid["triggered"] and invalid["points"]==0

# Confirms event vendors can submit without a portfolio or predefined package.
def test_portfolio_and_package_fields_are_optional_and_neutral():
    result=analyze_vendor(vendor(portfolio_link=None,package_name=None,package_details=None,price_or_range=None),[])
    package=next(item for item in result["trust_evidence"] if item["code"]=="package_transparency")
    assert not package["earned"] and package["points"]==0
    assert "neutral" in package["reason"].lower()
