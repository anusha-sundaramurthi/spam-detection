"""
Purpose: Owns the three isolated MongoDB collections—submissions, assessments,
and upload records—plus their indexes and compatibility timestamps.
"""

import os
from datetime import datetime, timezone
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "vendor_trust_demo")

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
database = client[MONGODB_DB]
submissions = database["submissions"]
assessments = database["assessments"]
upload_records = database["upload_records"]


# Verifies MongoDB, creates indexes, and safely upgrades legacy documents.
def initialize_database() -> None:
    """Create non-destructive indexes within the dedicated demo database."""
    client.admin.command("ping")
    submissions.create_index([("created_at", DESCENDING)])
    assessments.create_index([("submission_id", ASCENDING)], unique=True)
    assessments.create_index([("risk_level", ASCENDING)])
    assessments.create_index([("created_at", DESCENDING)])
    assessments.create_index([("admin_feedback.verdict", ASCENDING)])
    upload_records.create_index([("storage_name", ASCENDING)], unique=True)
    upload_records.create_index([("owner", ASCENDING), ("linked", ASCENDING)])
    upload_records.create_index([("submission_id", ASCENDING), ("kind", ASCENDING)])
    # Make databases created by earlier demo revisions compatible with the role workflow.
    submissions.update_many({"vendor_id": {"$exists": False}}, {"$set": {"vendor_id": "vendor@example.com"}})
    now = datetime.now(timezone.utc)
    submissions.update_many({"created_at": {"$exists": False}}, {"$set": {"created_at": now}})
    submissions.update_many({"updated_at": {"$exists": False}}, [{"$set": {"updated_at": {"$ifNull": ["$assessed_at", "$created_at"]}}}])
    assessments.update_many({"created_at": {"$exists": False}}, {"$set": {"created_at": now}})
    assessments.update_many({"updated_at": {"$exists": False}}, [{"$set": {"updated_at": {"$ifNull": ["$assessed_at", "$created_at"]}}}])
    upload_records.update_many({"created_at": {"$exists": False}}, [{"$set": {"created_at": {"$ifNull": ["$uploaded_at", now]}}}])
    upload_records.update_many({"updated_at": {"$exists": False}}, [{"$set": {"updated_at": "$created_at"}}])
    # Copy embedded legacy assessment/workflow data before removing it from raw submissions.
    assessment_fields = {"assessment_version", "assessment_status", "assessed_at", "rule_assessment", "risk_factors",
                         "trust_factors", "mandatory_services", "ai_assessment", "combined_assessment", "intelligence",
                         "trust_score", "risk_score", "confidence", "risk_level", "admin_feedback", "image_assessments",
                         "image_assessment_summary", "method", "scoring_model", "fallback_used"}
    assessment_fields.add("score_explanation")
    for row in submissions.find():
        migrated = {key: row[key] for key in assessment_fields if key in row}
        migrated.update(status=row.get("status", "pending"), assessment_status=row.get("assessment_status", migrated.get("assessment_status", "pending")))
        for key in ("approved_at", "approved_by"):
            if key in row: migrated[key] = row[key]
        assessments.update_one({"submission_id": row["_id"]}, {"$set": migrated,
            "$setOnInsert": {"submission_id": row["_id"], "created_at": row.get("assessed_at", row["created_at"]),
                             "updated_at": row.get("updated_at", row["created_at"])}}, upsert=True)
    # Supply safe compatibility values for records made before package fields became mandatory.
    submissions.update_many({"package_name": {"$exists": False}}, {"$set": {"package_name": "Legacy service package"}})
    submissions.update_many({"package_details": {"$exists": False}}, {"$set": {"package_details": "Package details were not captured by the earlier demo version."}})
    submissions.update_many({"price_or_range": {"$exists": False}}, {"$set": {"price_or_range": "Not provided"}})
    submissions.update_many({"address_line1": {"$exists": False}}, {"$set": {"address_line1": "Legacy address not provided"}})
    submissions.update_many({"address_line2": {"$exists": False}}, {"$set": {"address_line2": "Legacy address not provided"}})
    submissions.update_many({"city": {"$exists": False}}, [{"$set": {"city": {"$ifNull": ["$location", "Not provided"]}}}])
    submissions.update_many({"state": {"$exists": False}}, {"$set": {"state": "Not provided"}})
    submissions.update_many({"country": {"$exists": False}}, {"$set": {"country": "Not provided"}})
    submissions.update_many({"pincode": {"$exists": False}}, {"$set": {"pincode": "000"}})
    submissions.update_many({}, {"$unset": {"delivery_timeline": "", "location": ""}})
    submissions.update_many(
        {"portfolio_link": {"$exists": False}},
        {"$set": {"portfolio_link": None}},
    )
    # Enforce that submissions contain only form fields, linkage, and submission timestamps.
    non_raw_fields = assessment_fields | {"status", "approved_at", "approved_by", "email_normalized", "phone_normalized",
        "images", "file", "scoring_model", "fallback_used", "similar_count", "feedback_verdict"}
    submissions.update_many({}, {"$unset": {key: "" for key in non_raw_fields}})
