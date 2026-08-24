"""
Purpose: Inserts realistic trusted and spam vendor examples into an empty demo
database and processes them through the same automatic assessment pipeline.
"""
from datetime import datetime, timezone
from .database import assessments, submissions
from .intelligence import build_intelligence
from .llm_scoring import assess_with_local_llm, combine
from .schemas import VendorInput
from .scoring import MANDATORY_SCORING_SERVICES, analyze_vendor

SEEDS=[
VendorInput(name="Maya Chen Photography",email="maya@northstarstudio.co",phone="+1 415 555 0182",website="https://northstarstudio.co",address_line1="14 Northstar Avenue",address_line2="Studio 3",city="Chennai",state="Tamil Nadu",country="India",pincode="600001",gst_number="33ABCDE1234F1Z5",portfolio_link="https://instagram.com/northstarstudio",service_title="Wedding & event photography",category="Photography & Videography",business_registration="CA-NS-48291",social_links=["https://linkedin.com/in/mayachen"],description="We photograph weddings, corporate events, and celebrations for growing teams and families. Our process includes a pre-event consultation, full-day coverage, candid and posed shots, professional editing, and a private online gallery for clients.",package_name="Full Day Wedding Coverage",package_details="Two photographers, eight hours of coverage, 400+ edited photos, private online gallery, and a USB drive with high-resolution files.",price_or_range="$3,500-$5,000",special_offer="One complimentary engagement shoot included."),
VendorInput(name="Quick Cash",email="winner@mailinator.com",phone="5550001122",website="https://bit.ly/free-money",address_line1="Unknown road",address_line2="Unknown building",city="Unknown",state="Unknown",country="India",pincode="000",portfolio_link="https://bit.ly/free-money",service_title="GUARANTEED INSTANT PROFIT 🚀🚀🚀",category="Other",social_links=[],description="ACT NOW!!! 100% FREE!!! CLICK HERE 🚀🚀🚀🚀🚀🚀",package_name="Instant Winner",package_details="Buy now and receive guaranteed profits with no questions asked.",price_or_range="$99",special_offer="Limited time 100% free bonus")]

# Seeds assessed example records only when the submissions collection is empty.
def seed_if_empty():
    """Create assessed examples only when the dedicated demo collection is empty."""
    if submissions.count_documents({}): return
    prior=[]
    for data in SEEDS:
        now=datetime.now(timezone.utc); rules=analyze_vendor(data,prior); ai=assess_with_local_llm(data,rules); combined=combine(rules,ai); intelligence=build_intelligence(data,rules,ai,combined)
        assessment_status="complete" if ai["status"]=="complete" else "ai_unavailable"
        doc=data.model_dump(exclude={"images","file"})|{"created_at":now,"updated_at":now,"vendor_id":"vendor@example.com"}
        result=submissions.insert_one(doc)
        risk_reasons=[factor["reason"] for factor in ai["risk_factors"] if factor.get("points",0)>0]
        explanation={"risk":{"starting_score":0,"points_added":combined.get("risk_score"),"final_score":combined.get("risk_score"),"reasons":risk_reasons,"explanation":"Risk begins at 0; the model adds points only for identified spam-risk evidence."},"trust":{"starting_score":10,"points_awarded":combined.get("trust_score"),"points_reduced":round(10-(combined.get("trust_score") or 0),1) if ai["status"]=="complete" else None,"final_score":combined.get("trust_score"),"awarded_reasons":[factor["reason"] for factor in ai["trust_factors"] if factor.get("points",0)>0],"reduction_reasons":risk_reasons or [ai.get("summary")],"explanation":"Trust is shown out of 10; points not awarded are displayed as the reduction from the maximum."}}
        assessments.insert_one({"submission_id":result.inserted_id,"status":"pending","created_at":now,"updated_at":now,"assessed_at":now,"assessment_version":"ai-image-v3","assessment_status":assessment_status,"admin_feedback":[],"image_assessments":[],"image_assessment_summary":{"total":0,"complete":0,"unavailable":0,"relevant":0,"irrelevant":0,"duplicates":0,"spam":0},"rule_assessment":rules,"risk_factors":ai["risk_factors"],"trust_factors":ai["trust_factors"],"mandatory_services":MANDATORY_SCORING_SERVICES,"ai_assessment":ai,"combined_assessment":combined,"score_explanation":explanation,"intelligence":intelligence,**combined})
        prior.append({"id":str(result.inserted_id),"email":data.email,"phone":data.phone,"description":data.description})
