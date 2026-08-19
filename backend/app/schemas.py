"""
Purpose: Defines all validated API request and response contracts while keeping
vendor-facing responses deliberately free of private trust and spam scores.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class LoginInput(BaseModel):
    username: str
    password: str


class VendorInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    phone: str = Field(min_length=7, max_length=40)
    website: str | None = Field(default=None, max_length=500)
    service_title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    category: str = Field(min_length=2, max_length=80)
    social_links: list[str] = Field(default_factory=list, max_length=8)
    business_registration: str | None = Field(default=None, max_length=120)
    package_name: str = Field(min_length=2, max_length=120)
    package_details: str = Field(min_length=10, max_length=2000)
    price_or_range: str = Field(min_length=1, max_length=120)
    delivery_timeline: str = Field(min_length=2, max_length=160)
    special_offer: str | None = Field(default=None, max_length=500)

    # Trims mandatory text fields and rejects whitespace-only values.
    @field_validator("name", "phone", "service_title", "description", "category", "package_name", "package_details", "price_or_range", "delivery_timeline")
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


class AdminDetail(AdminSummary):
    phone: str
    website: str | None
    description: str
    social_links: list[str]
    business_registration: str | None
    package_name: str
    package_details: str
    price_or_range: str
    delivery_timeline: str
    special_offer: str | None = None
    risk_factors: list[dict] = []
    trust_factors: list[dict] = []
    mandatory_services: list[dict] = []
    rule_assessment: dict | None = None
    ai_assessment: dict | None = None
    combined_assessment: dict | None = None
