"""
Purpose: Verifies deterministic/AI weighting and safe rules-only fallback when
the local Ollama assessment is unavailable.
"""

from app.llm_scoring import combine, unavailable


RULES = {"trust_score": 8.0, "risk_score": 2.0, "confidence": 80, "risk_level": "low"}


# Confirms combined scoring retains the documented 60% rule weight.
def test_combined_score_keeps_rules_majority_weight():
    ai = {"status": "complete", "trust_score": 4.0, "risk_score": 8.0, "confidence": 60}
    result = combine(RULES, ai)
    assert result["trust_score"] == 6.4
    assert result["risk_score"] == 4.4
    assert result["method"] == "60% rules + 40% local AI"


# Confirms model failures never prevent deterministic scoring.
def test_unavailable_model_falls_back_to_rules():
    result = combine(RULES, unavailable("offline"))
    assert result["method"] == "rules_only"
    assert result["trust_score"] == 8.0
