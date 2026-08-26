"""
Purpose: Deterministic, rule-based spam signals for phone, email, and description
fields. Zero AI cost, runs before LLM scoring, and doubles as a fallback score
when the AI models are unavailable.
"""
import re
import phonenumbers
from phonenumbers import NumberParseException
import dns.resolver

DISPOSABLE_DOMAINS = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com"}
SPAM_PHRASES = ["guaranteed", "instant profit", "risk free", "act now", "limited time offer", "double your money", "100% return"]
EMOJI_PATTERN = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")

def check_phone(number: str, region: str = "IN") -> dict:
    # FIX: guard against None (not just "") so this is safe regardless of
    # whether the caller pre-checks the field. Previously phonenumbers.parse(None, ...)
    # raised TypeError, which isn't caught by the NumberParseException handler below
    # and crashed the caller.
    number = number or ""
    findings = []
    try:
        parsed = phonenumbers.parse(number, region)
        valid = phonenumbers.is_valid_number(parsed)
        if not valid:
            findings.append("invalid_or_unassigned_number")
    except NumberParseException:
        findings.append("unparseable_phone_format")
        valid = False
    digits = ''.join(filter(str.isdigit, number))
    # FIX: an empty/missing phone number produces digits == "", and
    # len(set("")) == 0 <= 2 was true, so a blank phone was incorrectly
    # flagged as a "repeated/sequential digit pattern" alongside the
    # (correct) invalid-format finding. Require at least one digit before
    # judging repetition, so a missing number is reported as missing, not
    # as a degenerate pattern.
    if digits and len(set(digits)) <= 2:
        findings.append("degenerate_digit_pattern")
    return {"valid_format": valid, "findings": findings}

def check_email(email: str) -> dict:
    # FIX: guard against None so a caller that doesn't pre-check the field
    # (e.g. build_evidence below) can't crash this with an AttributeError
    # on email.split(...).
    email = email or ""
    domain = email.split("@")[-1].lower()
    findings = []
    if domain in DISPOSABLE_DOMAINS:
        findings.append("disposable_email_domain")
    try:
        dns.resolver.resolve(domain, "MX")
    except Exception:
        findings.append("no_mx_record")
    return {"domain": domain, "findings": findings}

def check_description(text: str) -> dict:
    # FIX: guard against None so a caller that doesn't pre-check the field
    # can't crash this with an AttributeError on text.lower().
    text = text or ""
    findings = []
    lower = text.lower()
    hits = [p for p in SPAM_PHRASES if p in lower]
    if hits:
        findings.append(f"spam_phrases:{','.join(hits)}")
    emoji_count = len(EMOJI_PATTERN.findall(text))
    if emoji_count >= 2:
        findings.append(f"emoji_spam:{emoji_count}")
    alpha_chars = sum(1 for c in text if c.isalpha())
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, alpha_chars)
    if caps_ratio > 0.5 and len(text) > 15:
        findings.append(f"excess_caps:{caps_ratio:.0%}")
    return {"findings": findings}

def build_evidence(data) -> dict:
    """Bundle deterministic checks into the evidence dict ai_scoring.py expects."""
    vendor = data.model_dump()
    # FIX: vendor.get("phone", "") only falls back to "" when the key is
    # absent; a field explicitly stored as None still passed None straight
    # into check_phone/check_email/check_description. The functions above
    # are now individually hardened against None too, but guarding here as
    # well keeps this call site explicit and safe even if that changes later.
    return {
        "phone": check_phone(vendor.get("phone") or "", vendor.get("country") or "IN"),
        "email": check_email(vendor.get("email") or ""),
        "description": check_description(vendor.get("description") or ""),
    }

def rule_based_fallback_score(evidence: dict) -> dict:
    """Used ONLY when both AI models are unavailable — gives a non-blind floor score
    instead of leaving trust_score/risk_score as None."""
    risk = 0.0
    reasons = []
    if "disposable_email_domain" in evidence["email"]["findings"]:
        risk += 4; reasons.append("Disposable email domain detected")
    if "no_mx_record" in evidence["email"]["findings"]:
        risk += 2; reasons.append("Email domain has no valid mail server")
    if not evidence["phone"]["valid_format"]:
        risk += 3; reasons.append("Phone number failed format validation")
    if "degenerate_digit_pattern" in evidence["phone"]["findings"]:
        risk += 3; reasons.append("Phone number is a repeated/sequential pattern")
    for finding in evidence["description"]["findings"]:
        if finding.startswith("spam_phrases"):
            risk += 3; reasons.append("Description contains known spam phrases")
        elif finding.startswith("emoji_spam"):
            risk += 1.5; reasons.append("Excessive emoji usage in description")
        elif finding.startswith("excess_caps"):
            risk += 1; reasons.append("Excessive capitalization in description")
    risk = min(10.0, risk)
    return {
        "trust_score": round(10 - risk, 1), "risk_score": round(risk, 1), "confidence": 40,
        "risk_level": "high" if risk >= 6.5 else "medium" if risk >= 3 else "low",
        "method": "rule_based_fallback", "scoring_model": None, "fallback_reasons": reasons,
    }