"""
Purpose: Detects deterministic spam and trust evidence for local AI context;
these checks are explicitly zero-weight and never calculate final scores.
"""

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

SPAM_TERMS = {"guaranteed", "act now", "limited time", "risk free", "100% free", "click here", "buy now", "instant profit", "earn money fast", "no questions asked"}
SUSPICIOUS_URL_TERMS = {"bit.ly", "tinyurl.com", "t.co", "free-money", "crypto-giveaway", "login-verify"}
SOCIAL_HOSTS = {"linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "github.com"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF]")

# These checks are mandatory for every submission and are surfaced prominently in the admin UI.
MANDATORY_SCORING_SERVICES = [
    {"code": "primary_ai", "name": "Primary AI scoring: llama3.2:3b", "required": True},
    {"code": "backup_ai", "name": "Backup AI scoring: qwen2.5:3b", "required": True},
    {"code": "content_evidence", "name": "Zero-weight content-pattern evidence", "required": True},
    {"code": "duplicate_evidence", "name": "Zero-weight duplicate/campaign evidence", "required": True},
    {"code": "url_evidence", "name": "Zero-weight optional URL evidence", "required": True},
    {"code": "address_package_offer_evidence", "name": "Zero-weight address, package, and offer spam evidence", "required": True},
    {"code": "image_verification", "name": "Backend image integrity and duplicate evidence", "required": True},
]


# Checks whether a value is a complete HTTP(S) URL with a plausible host.
def valid_url(value: str | None) -> bool:
    """Require a complete HTTP(S) URL before any domain-based trust is awarded."""
    try:
        if not value:
            return False
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and "." in parsed.netloc
    except ValueError:
        return False


# Normalizes free text for punctuation-insensitive duplicate comparison.
def normalize(value: str) -> str:
    """Normalize free text so near-copy comparison ignores punctuation and spacing."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", value.lower())).strip()


# Applies deterministic checks only to produce explainable zero-weight evidence.
def analyze_vendor(data, prior_submissions: list[dict]) -> dict:
    """Return factual evidence without producing or influencing any score."""
    risk, trust = [], []

    # Adds one possible spam-risk factor to the auditable ledger.
    def risk_factor(code, label, _points, reason, triggered):
        risk.append({"code": code, "label": label, "points": 0, "max_points": 0,
                     "triggered": triggered, "reason": reason, "source": "deterministic_evidence", "scoring_weight": 0})

    # Adds one possible positive trust factor to the auditable ledger.
    def trust_factor(code, label, _points, reason, earned):
        trust.append({"code": code, "label": label, "points": 0, "max_points": 0,
                      "earned": earned, "reason": reason, "source": "deterministic_evidence", "scoring_weight": 0})

    domain = data.email.rsplit("@", 1)[-1].lower() if data.email and "@" in data.email else ""
    website_present = bool(data.website and data.website.strip())
    website_ok = valid_url(data.website)
    risk_factor("invalid_url", "Invalid optional website URL", .5, "Supplied website is not a complete HTTP(S) URL." if website_present and not website_ok else "No website supplied; no penalty." if not website_present else "Website URL is structurally valid.", website_present and not website_ok)
    suspicious_url = website_present and any(term in data.website.lower() for term in SUSPICIOUS_URL_TERMS)
    risk_factor("suspicious_url", "Suspicious or shortened URL", 1.0, "Website contains a shortened or suspicious URL pattern." if suspicious_url else "No suspicious URL pattern found.", suspicious_url)

    text_fields = {
        "service title": data.service_title, "description": data.description,
        "address": " ".join([data.address_line1, data.address_line2, data.city, data.state, data.country, data.pincode]),
        "package name": data.package_name or "", "package details": data.package_details or "",
        "price": data.price_or_range or "", "special offer": data.special_offer or "",
    }
    combined_text = " ".join(text_fields.values()).lower()
    spam_hits = sorted(term for term in SPAM_TERMS if term in combined_text)
    risk.append({"code": "spam_keywords", "label": "Spam and urgency phrases", "points": 0, "max_points": 0,
                 "triggered": bool(spam_hits), "reason": f"Matched: {', '.join(spam_hits)}." if spam_hits else "No common spam phrases found.",
                 "source": "deterministic_evidence", "scoring_weight": 0})
    field_hits = {field: sorted(term for term in SPAM_TERMS if term in value.lower())
                  for field, value in text_fields.items() if value and any(term in value.lower() for term in SPAM_TERMS)}
    risk_factor("spam_field_locations", "Spam phrases by submitted field", 0,
                "; ".join(f"{field}: {', '.join(hits)}" for field, hits in field_hits.items()) if field_hits else
                "No common spam phrases found in address, package, price, or offer fields.", bool(field_hits))

    verified_images = [image for image in data.images if image.get("image_verified")]
    hashes = [image.get("sha256") for image in verified_images if image.get("sha256")]
    prior_hashes = {image.get("sha256") for old in prior_submissions for image in old.get("images", []) if image.get("sha256")}
    duplicate_images = len(hashes) != len(set(hashes)) or bool(set(hashes) & prior_hashes)
    invalid_images = bool(data.images) and len(verified_images) != len(data.images)
    risk_factor("invalid_image", "Invalid or unverifiable service image", 0,
                "One or more image records failed backend integrity verification." if invalid_images else
                f"{len(verified_images)} image(s) passed backend format, decode, and dimension verification.", invalid_images)
    risk_factor("duplicate_image", "Duplicate service image", 0,
                "The same image content appears more than once or matches an earlier submission." if duplicate_images else
                "No duplicate image content found in this or prior submissions.", duplicate_images)
    letters = [c for c in combined_text if c.isalpha()]; caps_ratio = sum(c.isupper() for c in data.description) / max(1, len(letters)); emojis = len(EMOJI_RE.findall(combined_text))
    noisy = (len(letters) >= 20 and caps_ratio > .35) or emojis > 5
    risk_factor("noisy_content", "Excessive caps or emojis", 1.5, f"Uppercase ratio {caps_ratio:.0%}; {emojis} emojis." if noisy else "Capitalization and emoji use are reasonable.", noisy)

    word_count = len(data.description.split()); too_short = word_count < 20
    risk_factor("thin_description", "Thin service description", 1.5, f"Only {word_count} words; 20+ expected." if too_short else f"Description contains {word_count} words.", too_short)
    normalized = normalize(data.description)
    copied = next((old for old in prior_submissions if len(normalized) > 40 and SequenceMatcher(None, normalized, normalize(old["description"])).ratio() > .92), None)
    risk_factor("copied_description", "Copied description", 1.0, f"Closely matches submission #{copied['id']}." if copied else "Description is distinct from prior records.", bool(copied))
    words = normalized.split(); unique_ratio = len(set(words)) / max(1, len(words))
    repetitive = len(words) >= 12 and unique_ratio < .55
    risk_factor("repetitive_content", "Repetitive or keyword-stuffed description", 1.0, f"Only {unique_ratio:.0%} of words are unique." if repetitive else "No strong repetition or keyword stuffing found.", repetitive)
    duplicate = next((old for old in prior_submissions if normalize(old["description"]) == normalized), None)
    risk_factor("duplicate_submission", "Exact duplicate submission", .5, f"Description duplicates submission #{duplicate['id']}." if duplicate else "No exact duplicate submission found.", bool(duplicate))

    registration = bool(data.business_registration and len(data.business_registration.strip()) >= 5)
    trust_factor("registration", "Business registration supplied", 2.0, "Registration identifier supplied." if registration else "No registration identifier supplied.", registration)
    socials = [u for u in data.social_links if valid_url(u) and any(h in urlparse(u).netloc.lower() for h in SOCIAL_HOSTS)]
    social_points = min(1.5, len(socials) * .5)
    trust.append({"code": "social_presence", "label": "Recognized social presence", "points": 0, "max_points": 0,
                  "earned": bool(socials), "reason": f"{len(socials)} recognized profile(s)." if socials else "No recognized profiles supplied.",
                  "source": "deterministic_evidence", "scoring_weight": 0})
    domain_match = website_ok and domain not in {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com"} and domain.removeprefix("www.") == urlparse(data.website).netloc.lower().removeprefix("www.")
    trust_factor("domain_match", "Business email matches website", 2.0, "Email and website domains match." if domain_match else "Domains do not match or email is consumer-hosted.", domain_match)
    trust_factor("description_depth", "Detailed service description", 1.5, f"Description contains {word_count} words." if not too_short else "Description lacks operational detail.", not too_short)
    package_complete = bool(data.package_name and data.package_details and data.price_or_range)
    trust_factor("package_transparency", "Optional package transparency", 1.5, "Package, inclusions, and price/range supplied." if package_complete else "Optional package or pricing details were not supplied; this is neutral.", package_complete)
    contact_complete = bool(data.email) and len(re.sub(r"\D", "", data.phone)) >= 7
    trust_factor("contact_completeness", "Authenticated contact information", 1.5, "Login email and phone are available." if contact_complete else "Phone contact is incomplete.", contact_complete)

    return {"mode": "evidence_only", "scoring_weight": 0, "risk_evidence": risk, "trust_evidence": trust}
