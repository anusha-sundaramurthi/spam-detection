"""
Purpose: Verifies AI-only score mapping, factor-ledger normalization, and the
no-score state used when both local models fail.
"""
from app import llm_scoring
from app.llm_scoring import AIResult, combine, ground_factor_reasons, harmonize_model_scores, normalize_factors, repair_score_scale, unavailable, validate_score_consistency

# Confirms the final score is copied from AI without deterministic weighting.
def test_final_score_is_ai_only():
    ai={"status":"complete","model":"qwen3:1.7b","trust_score":4.0,"risk_score":8.0,"confidence":60}
    result=combine({"scoring_weight":0},ai)
    assert result["trust_score"]==4.0 and result["risk_score"]==8.0
    assert result["method"]=="AI-only local scoring" and result["scoring_model"]=="qwen3:1.7b"

# Confirms factor arithmetic is normalized to the exact model score.
def test_ai_factor_points_match_score():
    factors=normalize_factors([{"label":"Urgency","reason":"Act now","points":2},{"label":"Guarantee","reason":"Guaranteed result","points":1}],6.0,"risk")
    assert sum(item["points"] for item in factors)==6.0

# Confirms a clean model result may truthfully return no risk factors.
def test_clean_result_accepts_empty_risk_factors():
    parsed=llm_scoring.AIResult(spam_probability=0,trust_score=8,risk_score=0,confidence=80,
        risk_factors=[],trust_factors=[{"label":"Clear service","reason":"Specific deliverables supplied","points":8}],
        summary="No spam evidence found.")
    assert parsed.risk_factors==[] and normalize_factors([],0,"risk")==[]

# Confirms explicit spam evidence cannot be paired with a misleading zero-risk score.
def test_contradictory_zero_risk_result_is_rejected():
    parsed=AIResult(spam_probability=0,trust_score=10,risk_score=0,confidence=100,risk_factors=[],
        trust_factors=[{"label":"Details","reason":"Package details supplied","points":10}],
        summary="Suspicious urgency was detected.")
    evidence={"risk_evidence":[{"code":"spam_keywords","triggered":True}]}
    try:
        validate_score_consistency(parsed,evidence)
        assert False, "contradictory result should be rejected"
    except ValueError as exc:
        assert "zero-risk" in str(exc)

# Confirms Gemma-style percentage scores are safely converted to the required scale.
def test_percentage_scale_scores_are_repaired_before_validation():
    repaired=repair_score_scale({"trust_score":20,"risk_score":75,"confidence":80,
        "risk_factors":[{"points":75}],"trust_factors":[{"points":20}]})
    assert repaired["trust_score"]==2 and repaired["risk_score"]==7.5
    assert repaired["risk_factors"][0]["points"]==7.5

# Confirms high model-reported spam probability cannot coexist with inflated trust.
def test_high_spam_probability_harmonizes_risk_and_trust():
    result=harmonize_model_scores({"spam_probability":95,"risk_score":7.5,"trust_score":7})
    assert result["risk_score"]==9.5 and result["trust_score"]==0.5

# Confirms explicit spam evidence cannot be displayed as an earned trust reason.
def test_factor_reasons_are_grounded_in_correct_evidence_ledger():
    model={"risk_factors":[],"trust_factors":[{"label":"Spam","reason":"ACT NOW matched","points":1}]}
    evidence={"risk_evidence":[{"label":"Spam phrases","reason":"Matched: act now.","triggered":True}],
              "trust_evidence":[{"label":"Registration","reason":"Registration supplied.","earned":True}]}
    grounded=ground_factor_reasons(model,evidence)
    assert grounded["risk_factors"][0]["reason"]=="Matched: act now."
    assert grounded["trust_factors"][0]["reason"]=="Registration supplied."

# Confirms a model cannot claim a backend-validated URL is missing its scheme.
def test_contradictory_url_hallucination_is_rejected():
    model={"risk_score":9,"risk_factors":[{"label":"Invalid URL",
        "reason":"URL lacks a proper scheme.","points":9}],"trust_factors":[]}
    evidence={"risk_evidence":[{"code":"invalid_url","triggered":False},
                               {"code":"suspicious_url","triggered":False}],"trust_evidence":[]}
    try:
        ground_factor_reasons(model,evidence)
        assert False, "contradictory URL reason should be rejected"
    except ValueError as exc:
        assert "contradict" in str(exc)

# Confirms dual-model failure never manufactures a deterministic score.
def test_both_models_unavailable_blocks_scoring():
    result=combine({},unavailable(["primary failed","backup failed"]))
    assert result["method"]=="ai_unavailable"
    assert result["trust_score"] is None and result["risk_score"] is None

# Confirms Llama is attempted only after the primary Qwen model fails.
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
