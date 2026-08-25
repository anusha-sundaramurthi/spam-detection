"""
Purpose: Verifies AI-only score mapping, factor-ledger normalization, and the
no-score state used when both local models fail.
"""
from app import llm_scoring
from app.llm_scoring import AIResult, combine, normalize_factors, repair_score_scale, unavailable

# Confirms the final score is copied from AI without deterministic weighting.
def test_final_score_is_ai_only():
    ai={"status":"complete","model":"qwen3:1.7b","spam_probability":73,"trust_score":4.0,"risk_score":8.0,"confidence":60}
    result=combine({"scoring_weight":0},ai)
    assert result["trust_score"]==4.0 and result["risk_score"]==8.0
    assert result["spam_score"]==7.3
    assert result["method"]=="AI-only local scoring" and result["scoring_model"]=="qwen3:1.7b"

# Confirms factor arithmetic is normalized to the exact model score.
def test_ai_factor_points_match_score():
    factors=normalize_factors([{"label":"Urgency","reason":"Act now","points":2},{"label":"Guarantee","reason":"Guaranteed result","points":1}],6.0,"risk")
    assert sum(item["points"] for item in factors)==6.0

# Confirms clean model output may contain no spam-risk factors.
def test_clean_result_accepts_empty_risk_factors():
    parsed=AIResult(spam_probability=0,trust_score=8,risk_score=0,confidence=80,risk_factors=[],
        trust_factors=[{"label":"Details","reason":"Clear service details supplied","points":8}],summary="Clean")
    assert parsed.risk_factors==[] and normalize_factors([],0,"risk")==[]

# Confirms Gemma percentage-scale scores are converted before strict validation.
def test_percentage_scores_are_repaired():
    repaired=repair_score_scale({"trust_score":20,"risk_score":75,"risk_factors":[{"points":75}]})
    assert repaired["trust_score"]==2 and repaired["risk_score"]==7.5

# Confirms dual-model failure never manufactures a deterministic score.
def test_both_models_unavailable_blocks_scoring():
    result=combine({},unavailable(["primary failed","backup failed"]))
    assert result["method"]=="ai_unavailable"
    assert result["trust_score"] is None and result["risk_score"] is None
    assert result["spam_score"] is None

# Confirms Gemma is attempted only after the primary Qwen model fails.
def test_qwen_is_used_as_backup(monkeypatch):
    calls=[]
    def attempt(_data,_evidence,model):
        calls.append(model)
        if model==llm_scoring.PRIMARY_MODEL:return None,"primary failed"
        return {"spam_probability":40,"trust_score":6,"risk_score":4,"confidence":70,"risk_factors":[],"trust_factors":[],"spam_indicators":[],"trust_indicators":[],"summary":"fallback"},None
    monkeypatch.setattr(llm_scoring,"attempt_model",attempt)
    result=llm_scoring.assess_with_local_llm(object(),{})
    assert calls==[llm_scoring.PRIMARY_MODEL,llm_scoring.BACKUP_MODEL]
    assert result["model"]==llm_scoring.BACKUP_MODEL and result["fallback_used"] is True
