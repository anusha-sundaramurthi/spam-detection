"""
Purpose: Verifies evidence highlighting, AI-only counterfactuals, model
provenance, and coordinated-submission campaign detection.
"""

from types import SimpleNamespace
from bson import ObjectId

from app.intelligence import build_intelligence, campaign_metadata, find_similar_submissions


# Builds minimal factor data used by explainability tests.
def assessment_data():
    vendor = SimpleNamespace(service_title="ACT NOW design", description="Buy now for guaranteed growth", package_details="Design package", special_offer=None)
    evidence = {"mode": "evidence_only", "scoring_weight": 0, "risk_evidence": [], "trust_evidence": []}
    ai = {"status": "complete", "model": "qwen2.5:3b", "primary_model": "llama3.2:3b", "backup_model": "qwen2.5:3b", "fallback_used": True,
          "risk_score": 9.0, "risk_factors": [{"code": "ai_risk_1", "label": "Spam phrases", "points": 3.0}], "spam_indicators": ["Unrealistic guarantee"]}
    combined = {"risk_score": 9.0}
    return vendor, evidence, ai, combined


# Confirms exact phrases, fallback provenance, and AI counterfactual impact are explainable.
def test_intelligence_explains_score_and_fallback():
    result = build_intelligence(*assessment_data())
    assert {span["text"].lower() for span in result["evidence_map"]} >= {"act now", "buy now", "guaranteed"}
    assert result["model_provenance"]["fallback_used"] is True
    assert result["counterfactuals"][0]["estimated_risk_without_factor"] == 6.0


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
