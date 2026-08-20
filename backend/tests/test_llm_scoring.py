"""
Purpose: Verifies AI-only score mapping, factor-ledger normalization, and the
no-score state used when both local models fail.
"""
from app import llm_scoring
from app.llm_scoring import combine, normalize_factors, unavailable

# Confirms the final score is copied from AI without deterministic weighting.
def test_final_score_is_ai_only():
    ai={"status":"complete","model":"llama3.2:3b","trust_score":4.0,"risk_score":8.0,"confidence":60}
    result=combine({"scoring_weight":0},ai)
    assert result["trust_score"]==4.0 and result["risk_score"]==8.0
    assert result["method"]=="AI-only local scoring" and result["scoring_model"]=="llama3.2:3b"

# Confirms factor arithmetic is normalized to the exact model score.
def test_ai_factor_points_match_score():
    factors=normalize_factors([{"label":"Urgency","reason":"Act now","points":2},{"label":"Guarantee","reason":"Guaranteed result","points":1}],6.0,"risk")
    assert sum(item["points"] for item in factors)==6.0

# Confirms dual-model failure never manufactures a deterministic score.
def test_both_models_unavailable_blocks_scoring():
    result=combine({},unavailable(["primary failed","backup failed"]))
    assert result["method"]=="ai_unavailable"
    assert result["trust_score"] is None and result["risk_score"] is None

# Confirms Qwen is attempted only after the primary Llama model fails.
def test_qwen_is_used_as_backup(monkeypatch):
    calls=[]
    def attempt(_data,_evidence,model):
        calls.append(model)
        if model==llm_scoring.PRIMARY_MODEL:return None,"primary failed"
        return {"trust_score":6,"risk_score":4,"confidence":70,"risk_factors":[],"trust_factors":[],"spam_indicators":[],"trust_indicators":[],"summary":"fallback"},None
    monkeypatch.setattr(llm_scoring,"attempt_model",attempt)
    result=llm_scoring.assess_with_local_llm(object(),{})
    assert calls==[llm_scoring.PRIMARY_MODEL,llm_scoring.BACKUP_MODEL]
    assert result["model"]==llm_scoring.BACKUP_MODEL and result["fallback_used"] is True
