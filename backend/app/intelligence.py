"""
Purpose: Builds explainable spam evidence, score counterfactuals, model
disagreement metadata, and privacy-safe cross-submission campaign matches.
"""

import hashlib
import re
from difflib import SequenceMatcher

from .scoring import SPAM_TERMS, normalize


# Converts a submitted text field into non-overlapping rule evidence spans.
def evidence_spans(field: str, value: str | None) -> list[dict]:
    """Locate exact spam phrases so the admin can see the evidence in context."""
    if not value:
        return []
    spans = []
    lowered = value.lower()
    for term in sorted(SPAM_TERMS, key=len, reverse=True):
        for match in re.finditer(re.escape(term), lowered):
            spans.append({"field": field, "start": match.start(), "end": match.end(),
                          "text": value[match.start():match.end()], "detectors": ["rule"],
                          "reason": f"Matched spam or urgency phrase: {term}."})
    return sorted(spans, key=lambda item: (item["start"], item["end"]))


# Produces stored explainability metadata from deterministic and AI outputs.
def build_intelligence(data, rules: dict, ai: dict, combined: dict) -> dict:
    """Create evidence, counterfactual impacts, and rule/AI disagreement details."""
    evidence = []
    for field in ("service_title", "description", "package_details", "special_offer"):
        evidence.extend(evidence_spans(field, getattr(data, field, None)))
    ai_risk = ai.get("risk_score") if ai.get("status") == "complete" else None
    rule_risk = rules["risk_score"]
    gap = round(abs(rule_risk - ai_risk), 1) if ai_risk is not None else None
    disagreement = "unavailable" if gap is None else "high" if gap >= 4 else "medium" if gap >= 2 else "low"
    weight = .6 if ai_risk is not None else 1
    counterfactuals = [{"factor_code": factor["code"], "label": factor["label"],
        "current_risk": combined["risk_score"], "estimated_risk_without_factor": round(max(0, combined["risk_score"] - factor["points"] * weight), 1),
        "estimated_reduction": round(factor["points"] * weight, 1)}
        for factor in rules["risk_factors"] if factor["triggered"] and factor["points"] > 0]
    return {"evidence_map": evidence, "ai_evidence": ai.get("spam_indicators", []),
            "counterfactuals": counterfactuals, "disagreement": {"level": disagreement,
            "gap": gap, "rule_risk": rule_risk, "ai_risk": ai_risk,
            "reason": "Local AI was unavailable; rules were used alone." if gap is None else f"Rule and AI risk scores differ by {gap} points."}}


# Compares one record with all other records to find coordinated spam patterns.
def find_similar_submissions(row: dict, candidates: list[dict]) -> list[dict]:
    """Return explainable similarity matches without exposing them to vendors."""
    current = normalize(" ".join([row.get("service_title", ""), row.get("description", ""), row.get("package_details", "")]))
    current_phone = re.sub(r"\D", "", row.get("phone", ""))
    matches = []
    for other in candidates:
        if other.get("_id") == row.get("_id"):
            continue
        other_text = normalize(" ".join([other.get("service_title", ""), other.get("description", ""), other.get("package_details", "")]))
        text_similarity = SequenceMatcher(None, current, other_text).ratio() if current and other_text else 0
        same_phone = bool(current_phone and current_phone == re.sub(r"\D", "", other.get("phone", "")))
        same_website = bool(row.get("website") and row.get("website") == other.get("website"))
        similarity = max(text_similarity, .9 if same_phone else 0, .85 if same_website else 0)
        if similarity >= .78:
            reasons = ([f"{text_similarity:.0%} content similarity"] if text_similarity >= .78 else []) + (["same phone"] if same_phone else []) + (["same website"] if same_website else [])
            matches.append({"id": str(other["_id"]), "name": other.get("name", "Unknown"),
                "service_title": other.get("service_title", ""), "similarity": round(similarity * 100), "reasons": reasons})
    return sorted(matches, key=lambda item: item["similarity"], reverse=True)[:10]


# Creates a stable display identifier for a related-submission campaign.
def campaign_metadata(row: dict, matches: list[dict]) -> dict:
    """Summarize related submissions under a deterministic campaign identifier."""
    if not matches:
        return {"campaign_id": None, "similar_count": 0, "matches": []}
    ids = sorted([str(row["_id"])] + [match["id"] for match in matches])
    campaign_id = "SPAM-" + hashlib.sha256("|".join(ids).encode()).hexdigest()[:8].upper()
    return {"campaign_id": campaign_id, "similar_count": len(matches), "matches": matches}
