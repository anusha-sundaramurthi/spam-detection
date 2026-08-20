"""
Purpose: Defines the FastAPI application lifecycle and role-protected vendor and
admin workflows, including automatic assessment, migration, and approval.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import login, require_role
from .database import initialize_database, submissions, upload_records
from .intelligence import build_intelligence, campaign_metadata, find_similar_submissions
from .llm_scoring import assess_with_local_llm, combine
from .schemas import AdminDetail, AdminFeedbackInput, AdminSummary, LoginInput, VendorInput, VendorReceipt, VendorSubmission
from .scoring import MANDATORY_SCORING_SERVICES, analyze_vendor
from .seed import seed_if_empty
from .uploads import resolve_upload, store_upload_batch


# Initializes MongoDB and demo data when the API starts.
@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(); seed_if_empty(); yield


app = FastAPI(title="onivah Demo API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
vendor_only, admin_only = require_role("vendor"), require_role("admin")


# Validates and converts a URL identifier into a MongoDB ObjectId.
def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(404, "Submission not found")
    return ObjectId(value)


# Removes internal MongoDB fields and serializes ObjectId values for JSON.
def serialize(row):
    """Convert MongoDB-specific fields into safe JSON values at the API boundary."""
    result = dict(row); result["id"] = str(result.pop("_id"))
    result.pop("email_normalized", None); result.pop("phone_normalized", None); result.pop("vendor_id", None)
    return result


# Runs the complete automatic assessment and packages all stored admin evidence.
def assessment_fields(payload: VendorInput, prior: list[dict]) -> dict:
    """Keep deterministic, AI, combined, and explainability outputs synchronized."""
    evidence = analyze_vendor(payload, prior); ai = assess_with_local_llm(payload, evidence); combined = combine(evidence, ai)
    intelligence = build_intelligence(payload, evidence, ai, combined)
    return {"assessment_version": "ai-only-v1", "assessment_status": "complete" if ai["status"] == "complete" else "ai_unavailable", "assessed_at": datetime.now(timezone.utc),
        "rule_assessment": evidence, "risk_factors": ai.get("risk_factors", []), "trust_factors": ai.get("trust_factors", []),
        "mandatory_services": MANDATORY_SCORING_SERVICES, "ai_assessment": ai,
        "combined_assessment": combined, "intelligence": intelligence, **combined}


# Automatically upgrades and re-scores legacy records when required.
def ensure_current_assessment(row: dict) -> dict:
    """Automatically upgrade and rescore records created by earlier demo versions."""
    if row.get("assessment_version") == "ai-only-v1" and row.get("intelligence"):
        return row
    payload = VendorInput(**{key: row.get(key) for key in VendorInput.model_fields})
    prior = [{"id": str(x["_id"]), "email": x["email"], "phone": x["phone"], "description": x["description"]}
             for x in submissions.find({"_id": {"$ne": row["_id"]}})]
    update = assessment_fields(payload, prior)
    submissions.update_one({"_id": row["_id"]}, {"$set": update}); row.update(update); return row


# Adds dynamic campaign and reviewer metadata to an admin-only record.
def enrich_admin(row: dict) -> dict:
    """Compute cross-submission intelligence at read time so new matches appear immediately."""
    row = ensure_current_assessment(row)
    matches = find_similar_submissions(row, list(submissions.find()))
    feedback = row.get("admin_feedback", [])
    row["campaign"] = campaign_metadata(row, matches)
    row["similar_count"] = row["campaign"]["similar_count"]
    provenance = row["intelligence"].get("model_provenance", {})
    row["scoring_model"] = provenance.get("model")
    row["fallback_used"] = provenance.get("fallback_used", False)
    row["feedback_verdict"] = feedback[-1]["verdict"] if feedback else None
    return row


# Reports basic API and database mode metadata.
@app.get("/api/health")
def health(): return {"status": "ok", "mode": "demo", "database": "mongodb"}


# Authenticates a demo vendor or administrator account.
@app.post("/api/auth/login")
def authenticate(payload: LoginInput): return login(payload.username, payload.password)


# Accepts optional vendor media before the JSON submission is created.
@app.post("/api/vendor/uploads")
async def vendor_uploads(images: list[UploadFile] = File(default=[]), attachment: UploadFile | None = File(default=None), user=Depends(vendor_only)):
    """Validate and store up to five service images plus one supporting document."""
    stored = await store_upload_batch(images, attachment, user["sub"])
    records = stored["images"] + ([stored["file"]] if stored["file"] else [])
    if records: upload_records.insert_many([record | {"linked": False, "uploaded_at": datetime.now(timezone.utc)} for record in records])
    return stored


# Replaces client-supplied upload metadata with authoritative owned records.
def verified_uploads(payload: VendorInput, owner: str) -> VendorInput:
    """Prevent vendors from linking unknown or another vendor's uploaded files."""
    requested = [item.get("storage_name") for item in payload.images] + ([payload.file.get("storage_name")] if payload.file else [])
    if not requested:
        return payload
    records = list(upload_records.find({"storage_name": {"$in": requested}, "owner": owner, "linked": False}))
    by_name = {record["storage_name"]: {key: value for key, value in record.items() if key not in {"_id", "linked", "uploaded_at"}} for record in records}
    if len(requested) != len(set(requested)) or len(by_name) != len(requested) or any(name not in by_name for name in requested):
        raise HTTPException(400, "One or more uploads are invalid, already linked, or owned by another vendor")
    images = [by_name[item["storage_name"]] for item in payload.images]
    attachment = by_name[payload.file["storage_name"]] if payload.file else None
    return payload.model_copy(update={"images": images, "file": attachment})


# Stores and automatically assesses a vendor submission without exposing scores.
@app.post("/api/vendor/submissions", response_model=VendorReceipt, status_code=201)
def vendor_submit(payload: VendorInput, user=Depends(vendor_only)):
    """Persist the vendor record, then automatically score it without exposing scores."""
    payload = verified_uploads(payload.model_copy(update={"email": user["sub"]}), user["sub"])
    now = datetime.now(timezone.utc)
    prior = [{"id": str(x["_id"]), "email": x["email"], "phone": x["phone"], "description": x["description"]} for x in submissions.find()]
    assessment = assessment_fields(payload, prior)
    document = payload.model_dump() | {"created_at": now, "assessed_at": now, "vendor_id": user["sub"], "status": "pending",
        "assessment_status": "complete", "email_normalized": payload.email.lower(), "phone_normalized": re.sub(r"\D", "", payload.phone),
        "admin_feedback": [], **assessment}
    result = submissions.insert_one(document)
    storage_names = [item["storage_name"] for item in payload.images] + ([payload.file["storage_name"]] if payload.file else [])
    if storage_names: upload_records.update_many({"storage_name": {"$in": storage_names}}, {"$set": {"linked": True, "submission_id": result.inserted_id}})
    return VendorReceipt(id=str(result.inserted_id), status="pending", created_at=now)


# Lists only submissions owned by the authenticated vendor.
@app.get("/api/vendor/submissions", response_model=list[VendorSubmission])
def vendor_submissions(user=Depends(vendor_only)):
    return [serialize(x) for x in submissions.find({"vendor_id": user["sub"]}).sort("created_at", -1)]


# Lists all automatically assessed submissions for administrators.
@app.get("/api/admin/submissions", response_model=list[AdminSummary])
def admin_submissions(user=Depends(admin_only)):
    """Expose internal scores only through the administrator-protected collection view."""
    return [serialize(enrich_admin(x)) for x in submissions.find().sort("created_at", -1)]


# Returns a full admin-only assessment and evidence breakdown.
@app.get("/api/admin/submissions/{submission_id}", response_model=AdminDetail)
def admin_detail(submission_id: str, user=Depends(admin_only)):
    """Return the complete evidence ledger for human review."""
    row = submissions.find_one({"_id": oid(submission_id)})
    if not row: raise HTTPException(404, "Submission not found")
    return serialize(enrich_admin(row))


# Streams a stored submission upload only to authenticated administrators.
@app.get("/api/admin/uploads/{storage_name}")
def admin_upload(storage_name: str, user=Depends(admin_only)):
    """Protect service images and documents from unauthenticated public access."""
    row = submissions.find_one({"$or": [{"images.storage_name": storage_name}, {"file.storage_name": storage_name}]})
    if not row: raise HTTPException(404, "Upload is not linked to a submission")
    metadata = next((image for image in row.get("images", []) if image["storage_name"] == storage_name), row.get("file"))
    return FileResponse(resolve_upload(storage_name), media_type=metadata["content_type"], filename=metadata["original_name"])


# Records a human approval after automatic assessment completes.
@app.post("/api/admin/submissions/{submission_id}/approve", response_model=AdminDetail)
def approve(submission_id: str, user=Depends(admin_only)):
    """Allow a human decision only after automatic mandatory assessment finishes."""
    target = oid(submission_id); row = submissions.find_one({"_id": target})
    if not row: raise HTTPException(404, "Submission not found")
    row = enrich_admin(row)
    if row.get("assessment_status") != "complete": raise HTTPException(409, "Automatic assessment is still incomplete")
    update = {"status": "approved", "approved_at": datetime.now(timezone.utc), "approved_by": user["sub"]}
    submissions.update_one({"_id": target}, {"$set": update}); row.update(update)
    return serialize(row)


# Stores the administrator's judgment for false-positive and rule-quality analysis.
@app.post("/api/admin/submissions/{submission_id}/feedback", response_model=AdminDetail)
def save_feedback(submission_id: str, payload: AdminFeedbackInput, user=Depends(admin_only)):
    """Append human feedback without automatically changing scoring weights or approval state."""
    target = oid(submission_id); row = submissions.find_one({"_id": target})
    if not row: raise HTTPException(404, "Submission not found")
    row = enrich_admin(row)
    valid_codes = {factor["code"] for factor in row.get("risk_factors", [])}
    if any(code not in valid_codes for code in payload.factor_codes):
        raise HTTPException(422, "Feedback contains an unknown risk factor")
    feedback = payload.model_dump() | {"created_at": datetime.now(timezone.utc), "admin_id": user["sub"]}
    submissions.update_one({"_id": target}, {"$push": {"admin_feedback": feedback}})
    row.setdefault("admin_feedback", []).append(feedback)
    return serialize(enrich_admin(row))
