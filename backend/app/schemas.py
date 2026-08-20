"""
Purpose: Defines all validated API request and response contracts while keeping
vendor-facing responses deliberately free of private trust and spam scores.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class LoginInput(BaseModel):
    username: str
    password: str


class AdminFeedbackInput(BaseModel):
    verdict: str = Field(pattern="^(confirmed_spam|false_positive|accurate_low_risk|needs_review)$")
    notes: str | None = Field(default=None, max_length=1000)
    factor_codes: list[str] = Field(default_factory=list, max_length=20)


class VendorInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    phone: str = Field(min_length=7, max_length=40)
    website: str | None = Field(default=None, max_length=500)
    address_line1: str = Field(min_length=3, max_length=200)
    address_line2: str = Field(min_length=2, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    country: str = Field(min_length=2, max_length=100)
    pincode: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]{2,11}$")
    aadhaar_number: str | None = Field(default=None, pattern=r"^\d{12}$")
    gst_number: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    portfolio_link: str | None = Field(default=None, max_length=500)
    service_title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    category: str = Field(min_length=2, max_length=80)
    social_links: list[str] = Field(default_factory=list, max_length=8)
    business_registration: str | None = Field(default=None, max_length=120)
    package_name: str | None = Field(default=None, max_length=120)
    package_details: str | None = Field(default=None, max_length=2000)
    price_or_range: str | None = Field(default=None, max_length=120)
    special_offer: str | None = Field(default=None, max_length=500)
    images: list[dict] = Field(default_factory=list, max_length=5)
    file: dict | None = None

    # Trims mandatory text fields and rejects whitespace-only values.
    @field_validator("name", "phone", "address_line1", "address_line2", "city", "state", "country", "pincode", "service_title", "description", "category")
    @classmethod
    def strip_required(cls, value):
        if not value.strip(): raise ValueError("must not be blank")
        return value.strip()


class VendorReceipt(BaseModel):
    id: str
    status: str
    created_at: datetime
    message: str = "Submitted for admin review"


class VendorSubmission(VendorReceipt):
    service_title: str
    category: str


class AdminSummary(BaseModel):
    id: str
    created_at: datetime
    name: str
    email: str
    service_title: str
    category: str
    status: str
    assessment_status: str
    trust_score: float | None = None
    risk_score: float | None = None
    confidence: int | None = None
    risk_level: str | None = None
    scoring_model: str | None = None
    fallback_used: bool = False
    similar_count: int = 0
    feedback_verdict: str | None = None


class AdminDetail(AdminSummary):
    phone: str
    website: str | None
    address_line1: str
    address_line2: str
    city: str
    state: str
    country: str
    pincode: str
    aadhaar_number: str | None = None
    gst_number: str | None = None
    portfolio_link: str | None
    description: str
    social_links: list[str]
    business_registration: str | None
    package_name: str | None
    package_details: str | None
    price_or_range: str | None
    special_offer: str | None = None
    images: list[dict] = []
    file: dict | None = None
    risk_factors: list[dict] = []
    trust_factors: list[dict] = []
    mandatory_services: list[dict] = []
    rule_assessment: dict | None = None
    ai_assessment: dict | None = None
    combined_assessment: dict | None = None
    intelligence: dict = {}
    campaign: dict = {}
    admin_feedback: list[dict] = []
