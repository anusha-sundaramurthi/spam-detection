"""
Purpose: Owns the isolated MongoDB client, submissions collection, indexes,
and compatibility migrations for records created by earlier demo versions.
"""

import os
from datetime import datetime, timezone
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "vendor_trust_demo")

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
database = client[MONGODB_DB]
submissions = database["submissions"]
upload_records = database["upload_records"]


# Verifies MongoDB, creates indexes, and safely upgrades legacy documents.
def initialize_database() -> None:
    """Create non-destructive indexes within the dedicated demo database."""
    client.admin.command("ping")
    submissions.create_index([("created_at", DESCENDING)])
    submissions.create_index([("risk_level", ASCENDING)])
    submissions.create_index([("email_normalized", ASCENDING)])
    submissions.create_index([("phone_normalized", ASCENDING)])
    submissions.create_index([("admin_feedback.verdict", ASCENDING)])
    upload_records.create_index([("storage_name", ASCENDING)], unique=True)
    upload_records.create_index([("owner", ASCENDING), ("linked", ASCENDING)])
    # Make databases created by earlier demo revisions compatible with the role workflow.
    submissions.update_many({"vendor_id": {"$exists": False}}, {"$set": {"vendor_id": "vendor@example.com"}})
    submissions.update_many({"status": {"$exists": False}}, {"$set": {"status": "pending"}})
    submissions.update_many({"assessment_status": {"$exists": False}}, {"$set": {"assessment_status": "complete"}})
    submissions.update_many({"admin_feedback": {"$exists": False}}, {"$set": {"admin_feedback": []}})
    now = datetime.now(timezone.utc)
    submissions.update_many({"created_at": {"$exists": False}}, {"$set": {"created_at": now}})
    submissions.update_many({"updated_at": {"$exists": False}}, [{"$set": {"updated_at": {"$ifNull": ["$assessed_at", "$created_at"]}}}])
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
        {"$or": [{"images": {"$exists": False}}, {"images": None}]},
        {"$set": {"images": []}},
    )
    submissions.update_many(
        {"portfolio_link": {"$exists": False}},
        {"$set": {"portfolio_link": None}},
    )
