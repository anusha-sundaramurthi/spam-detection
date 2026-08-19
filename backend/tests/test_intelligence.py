"""
Purpose: Verifies evidence highlighting, score counterfactuals, AI disagreement,
and coordinated-submission campaign detection.
"""

from types import SimpleNamespace
from bson import ObjectId

from app.intelligence import build_intelligence, campaign_metadata, find_similar_submissions


# Builds minimal factor data used by explainability tests.
def assessment_data():
    vendor = SimpleNamespace(service_title="ACT NOW design", description="Buy now for guaranteed growth", package_details="Design package", special_offer=None)
    rules = {"risk_score": 5.0, "risk_factors": [{"code": "spam_keywords", "label": "Spam phrases", "points": 3.0, "triggered": True}]}
    ai = {"status": "complete", "risk_score": 9.0, "spam_indicators": ["Unrealistic guarantee"]}
    combined = {"risk_score": 6.6}
    return vendor, rules, ai, combined


# Confirms exact phrases, disagreement, and counterfactual impact are explainable.
def test_intelligence_explains_score_and_disagreement():
    result = build_intelligence(*assessment_data())
    assert {span["text"].lower() for span in result["evidence_map"]} >= {"act now", "buy now", "guaranteed"}
    assert result["disagreement"]["level"] == "high"
    assert result["counterfactuals"][0]["estimated_risk_without_factor"] == 4.8


# Confirms lightly changed copy is grouped into a stable campaign.
def test_similar_submissions_form_campaign():
    target_id, other_id = ObjectId(), ObjectId()
    base = {"_id": target_id, "name": "One", "phone": "1111111", "website": None,
            "service_title": "Growth package", "description": "Guaranteed growth package for every small business with weekly reports", "package_details": "Reports and campaign setup"}
    other = base | {"_id": other_id, "name": "Two", "description": "Guaranteed growth package for every small business with weekly reporting"}
    matches = find_similar_submissions(base, [base, other])
    campaign = campaign_metadata(base, matches)
    assert matches and matches[0]["id"] == str(other_id)
    assert campaign["campaign_id"].startswith("SPAM-") and campaign["similar_count"] == 1
