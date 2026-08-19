"""
Purpose: Inserts realistic trusted and spam vendor examples into an empty demo
database and processes them through the same automatic assessment pipeline.
"""
from datetime import datetime, timezone
import re
from .database import submissions
from .llm_scoring import assess_with_local_llm, combine
from .schemas import VendorInput
from .scoring import MANDATORY_SCORING_SERVICES, score_vendor

SEEDS=[
VendorInput(name="Maya Chen",email="maya@northstarstudio.co",phone="+1 415 555 0182",website="https://northstarstudio.co",service_title="Accessible product design",category="Design",business_registration="CA-NS-48291",social_links=["https://linkedin.com/in/mayachen"],description="We design accessible web and mobile products for growing teams. Our process includes user research, interface design, prototype testing, design systems, and a documented accessibility review.",package_name="Product Design Sprint",package_details="Research workshop, five core screens, interactive prototype, accessibility audit, two revision rounds, and developer handoff.",price_or_range="$3,500-$5,000",delivery_timeline="4-6 weeks",special_offer="One follow-up accessibility review included."),
VendorInput(name="Quick Cash",email="winner@mailinator.com",phone="5550001122",website="https://bit.ly/free-money",service_title="GUARANTEED INSTANT PROFIT 🚀🚀🚀",category="Marketing",social_links=[],description="ACT NOW!!! 100% FREE!!! CLICK HERE 🚀🚀🚀🚀🚀🚀",package_name="Instant Winner",package_details="Buy now and receive guaranteed profits with no questions asked.",price_or_range="$99",delivery_timeline="Instant",special_offer="Limited time 100% free bonus")]

# Seeds assessed example records only when the submissions collection is empty.
def seed_if_empty():
    """Create assessed examples only when the dedicated demo collection is empty."""
    if submissions.count_documents({}): return
    prior=[]
    for data in SEEDS:
        now=datetime.now(timezone.utc); rules=score_vendor(data,prior); ai=assess_with_local_llm(data); combined=combine(rules,ai)
        doc=data.model_dump()|{"created_at":now,"assessed_at":now,"vendor_id":"vendor@example.com","status":"pending","assessment_status":"complete","email_normalized":data.email.lower(),"phone_normalized":re.sub(r"\D","",data.phone),"rule_assessment":rules,"risk_factors":rules["risk_factors"],"trust_factors":rules["trust_factors"],"mandatory_services":MANDATORY_SCORING_SERVICES,"ai_assessment":ai,"combined_assessment":combined,**combined}
        result=submissions.insert_one(doc); prior.append({"id":str(result.inserted_id),"email":data.email,"phone":data.phone,"description":data.description})
