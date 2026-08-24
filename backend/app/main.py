"""
Purpose: Defines the FastAPI application lifecycle and role-protected vendor and
admin workflows, including automatic assessment, migration, and approval.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import login, require_role
from .database import assessments, initialize_database, submissions, upload_records
from .document_assessment import assess_submission_document  # NEW
from .image_assessment import assess_submission_images
from .intelligence import build_intelligence, campaign_metadata, find_similar_submissions
from .llm_scoring import assess_with_local_llm, combine
from .schemas import AdminDetail, AdminFeedbackInput, AdminSummary, LoginInput, VendorInput, VendorReceipt, VendorSubmission
from .scoring import MANDATORY_SCORING_SERVICES, analyze_vendor
from .seed import seed_if_empty
from .uploads import resolve_upload, store_upload_batch


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(); seed_if_empty(); yield


app = FastAPI(title="onivah Demo API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
vendor_only, admin_only = require_role("vendor"), require_role("admin")


def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(404, "Submission not found")
    return ObjectId(value)


def serialize(row):
    """Convert MongoDB-specific fields into safe JSON values at the API boundary."""
    result = dict(row); result["id"] = str(result.pop("_id"))
    result.pop("email_normalized", None); result.pop("phone_normalized", None); result.pop("vendor_id", None)
    return result


def assessment_fields(payload: VendorInput, prior: list[dict]) -> dict:
    """Keep deterministic, AI, combined, and explainability outputs synchronized."""
    evidence = analyze_vendor(payload, prior); ai = assess_with_local_llm(payload, evidence); combined = combine(evidence, ai)
    intelligence = build_intelligence(payload, evidence, ai, combined)
    risk_reasons = [factor["reason"] for factor in ai.get("risk_factors", []) if factor.get("points", 0) > 0]
    trust_reduction = round(10 - (combined.get("trust_score") or 0), 1) if ai["status"] == "complete" else None
    score_explanation = {
        "risk": {"starting_score": 0, "points_added": combined.get("risk_score"), "final_score": combined.get("risk_score"),
                 "reasons": risk_reasons, "explanation": "Risk begins at 0; the model adds points only for identified spam-risk evidence."},
        "trust": {"starting_score": 10, "points_awarded": combined.get("trust_score"), "points_reduced": trust_reduction,
                  "final_score": combined.get("trust_score"), "awarded_reasons": [factor["reason"] for factor in ai.get("trust_factors", []) if factor.get("points", 0) > 0],
                  "reduction_reasons": risk_reasons or ([ai.get("summary")] if ai.get("summary") else []),
                  "explanation": "Trust is shown out of 10; points not awarded are displayed as the reduction from the maximum."},
    }
    return {"assessment_version": "ai-image-v3", "assessment_status": "complete" if ai["status"] == "complete" else "ai_unavailable", "assessed_at": datetime.now(timezone.utc),
        "rule_assessment": evidence, "risk_factors": ai.get("risk_factors", []), "trust_factors": ai.get("trust_factors", []),
        "mandatory_services": MANDATORY_SCORING_SERVICES, "ai_assessment": ai,
        "combined_assessment": combined, "score_explanation": score_explanation, "intelligence": intelligence, **combined}


# Reloads a newly stored MongoDB document and assesses only that authoritative record.
def assess_stored_submission(submission_id: ObjectId) -> None:
    """Enforce the save-first, fetch-from-database, destructure, then assess workflow."""
    row = submissions.find_one({"_id": submission_id})
    if not row:
        return
    media = list(upload_records.find({"submission_id": submission_id}))
    images = [{key: value for key, value in item.items() if key not in {"_id", "assessment"}}
              for item in media if item.get("kind") == "image"]
    attachment = next(({key: value for key, value in item.items() if key not in {"_id", "assessment"}}
                       for item in media if item.get("kind") == "file"), None)
    payload_data = {field: row.get(field) for field in VendorInput.model_fields}
    payload_data.update(images=images, file=attachment)
    payload = VendorInput(**payload_data)
    prior = [{"id": str(item["_id"]), "email": item.get("email"), "phone": item.get("phone"),
              "description": item.get("description", ""), "images": item.get("images", [])}
             for item in submissions.find({"_id": {"$ne": submission_id}})]
    prior_hashes = {item.get("sha256") for item in upload_records.find({"submission_id": {"$ne": submission_id}, "kind": "image"}) if item.get("sha256")}

    image_results = assess_submission_images(images, payload.model_dump(), prior_hashes)
    # NEW: run document detection (text extraction, Aadhaar/name verification,
    # AI relevance + trust/risk judgment). Previously this module was never called.
    document_result = assess_submission_document(attachment, payload.model_dump(), payload.aadhaar_number)

    now = datetime.now(timezone.utc)
    for result in image_results:
        upload_records.update_one({"submission_id": submission_id, "storage_name": result["storage_name"]},
                                  {"$set": {"assessment": result, "updated_at": now}})
    if document_result:
        upload_records.update_one({"submission_id": submission_id, "storage_name": document_result["storage_name"]},
                                  {"$set": {"assessment": document_result, "updated_at": now}})

    assessment = assessment_fields(payload, prior)
    complete_images = sum(item["status"] == "complete" for item in image_results)
    failed_components = []
    if image_results and complete_images != len(image_results):
        failed_components.append("image")
    if document_result and document_result["status"] != "complete":
        failed_components.append("document")
    if failed_components and assessment["assessment_status"] == "complete":
        assessment["assessment_status"] = "_".join(failed_components) + "_ai_unavailable"

    assessment.update(image_assessments=image_results, image_assessment_summary={
        "total": len(image_results), "complete": complete_images,
        "unavailable": len(image_results) - complete_images,
        "relevant": sum(item.get("relevance") == "relevant" for item in image_results),
        "irrelevant": sum(item.get("relevance") == "irrelevant" for item in image_results),
        "duplicates": sum(bool(item.get("duplicate")) for item in image_results),
        "spam": sum(item.get("spam_detected") is True for item in image_results),
    }, document_assessment=document_result, document_assessment_summary=({
        "status": document_result["status"],
        "relevance": document_result.get("relevance"),
        "spam_detected": document_result.get("spam_detected"),
        "trust_score": document_result.get("trust_score"),
        "risk_score": document_result.get("risk_score"),
        "aadhaar_match": document_result.get("aadhaar_verification", {}).get("match"),
        "name_match": document_result.get("name_verification", {}).get("found_in_document"),
    } if document_result else None), updated_at=now)

    assessments.update_one({"submission_id": submission_id}, {"$set": assessment,
                           "$setOnInsert": {"submission_id": submission_id, "status": "pending", "created_at": now,
                                            "admin_feedback": []}}, upsert=True)


def migrate_one(row: dict) -> None:
    """Upgrade a single legacy record to the current assessment version."""
    assess_stored_submission(row["_id"])


def joined_submission(row: dict) -> dict:
    """Keep storage normalized while preserving frontend response compatibility."""
    result = dict(row)
    assessment = assessments.find_one({"submission_id": row["_id"]}) or {}
    result.update({key: value for key, value in assessment.items() if key not in {"_id", "submission_id", "created_at", "updated_at"}})
    result["assessment_created_at"] = assessment.get("created_at")
    result["assessment_updated_at"] = assessment.get("updated_at")
    result.setdefault("status", "pending")
    result.setdefault("assessment_status", "pending")
    media = list(upload_records.find({"submission_id": row["_id"]}))
    cleaned = [{key: value for key, value in item.items() if key not in {"_id", "submission_id"}} for item in media]
    result["images"] = [item for item in cleaned if item.get("kind") == "image"]
    result["file"] = next((item for item in cleaned if item.get("kind") == "file"), None)
    result.setdefault("image_assessments", [item["assessment"] for item in result["images"] if item.get("assessment")])
    result.setdefault("image_assessment_summary", {"total": len(result["images"]), "complete": 0, "unavailable": len(result["images"]), "relevant": 0, "irrelevant": 0, "duplicates": 0, "spam": 0})
    result.setdefault("document_assessment", result["file"]["assessment"] if result["file"] and result["file"].get("assessment") else None)  # NEW
    result.setdefault("document_assessment_summary", None)  # NEW
    return result


def enrich_admin(row: dict) -> dict:
    """Compute cross-submission intelligence at read time using stored data only."""
    row = joined_submission(row)
    matches = find_similar_submissions(row, list(submissions.find()))
    feedback = row.get("admin_feedback", [])
    row["campaign"] = campaign_metadata(row, matches)
    row["similar_count"] = row["campaign"]["similar_count"]
    provenance = (row.get("intelligence") or {}).get("model_provenance", {})
    row["scoring_model"] = provenance.get("model")
    row["fallback_used"] = provenance.get("fallback_used", False)
    row["feedback_verdict"] = feedback[-1]["verdict"] if feedback else None
    return row


@app.get("/api/health")
def health(): return {"status": "ok", "mode": "demo", "database": "mongodb"}


@app.post("/api/auth/login")
def authenticate(payload: LoginInput): return login(payload.username, payload.password)


@app.post("/api/vendor/submissions", response_model=VendorReceipt, status_code=201)
async def vendor_submit(background_tasks: BackgroundTasks, payload_json: str = Form(...),
                        images: list[UploadFile] = File(default=[]), attachment: UploadFile | None = File(default=None),
                        user=Depends(vendor_only)):
    """Persist first and return a score-free receipt while backend assessment runs afterward."""
    try:
        payload = VendorInput.model_validate_json(payload_json).model_copy(update={"email": user["sub"]})
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors(include_url=False)) from exc
    stored = await store_upload_batch(images, attachment, user["sub"])
    payload = payload.model_copy(update=stored)
    now = datetime.now(timezone.utc)
    form_data = payload.model_dump(exclude={"images", "file"})
    document = form_data | {"created_at": now, "updated_at": now, "vendor_id": user["sub"]}
    result = submissions.insert_one(document)
    assessments.insert_one({"submission_id": result.inserted_id, "status": "pending", "assessment_status": "pending",
                            "admin_feedback": [], "created_at": now, "updated_at": now})
    records = stored["images"] + ([stored["file"]] if stored["file"] else [])
    if records:
        upload_records.insert_many([record | {"linked": True, "submission_id": result.inserted_id,
                                               "created_at": now, "updated_at": now} for record in records])
    background_tasks.add_task(assess_stored_submission, result.inserted_id)
    return VendorReceipt(id=str(result.inserted_id), status="pending", created_at=now)


@app.get("/api/vendor/submissions", response_model=list[VendorSubmission])
def vendor_submissions(user=Depends(vendor_only)):
    rows = []
    for submission in submissions.find({"vendor_id": user["sub"]}).sort("created_at", -1):
        workflow = assessments.find_one({"submission_id": submission["_id"]}, {"status": 1}) or {}
        row = dict(submission); row["status"] = workflow.get("status", "pending")
        rows.append(serialize(row))
    return rows


@app.get("/api/admin/submissions", response_model=list[AdminSummary])
def admin_submissions(user=Depends(admin_only)):
    """Expose internal scores only through the administrator-protected collection view."""
    return [serialize(enrich_admin(x)) for x in submissions.find().sort("created_at", -1)]


@app.get("/api/admin/submissions/{submission_id}", response_model=AdminDetail)
def admin_detail(submission_id: str, user=Depends(admin_only)):
    """Return the complete evidence ledger for human review."""
    row = submissions.find_one({"_id": oid(submission_id)})
    if not row: raise HTTPException(404, "Submission not found")
    return serialize(enrich_admin(row))


@app.post("/api/admin/migrate")
def migrate_stale(user=Depends(admin_only)):
    """Re-score legacy records on demand instead of silently on every read."""
    current_ids = set(assessments.distinct("submission_id", {"assessment_version": "ai-image-v3"}))
    stale = list(submissions.find({"_id": {"$nin": list(current_ids)}}))
    for row in stale:
        migrate_one(row)
    return {"status": "ok", "migrated": len(stale)}


@app.get("/api/admin/uploads/{storage_name}")
def admin_upload(storage_name: str, user=Depends(admin_only)):
    """Protect service images and documents from unauthenticated public access."""
    metadata = upload_records.find_one({"storage_name": storage_name, "linked": True})
    if not metadata: raise HTTPException(404, "Upload is not linked to a submission")
    return FileResponse(resolve_upload(storage_name), media_type=metadata["content_type"], filename=metadata["original_name"])


@app.post("/api/admin/submissions/{submission_id}/approve", response_model=AdminDetail)
def approve(submission_id: str, user=Depends(admin_only)):
    """Allow a human decision only after automatic mandatory assessment finishes."""
    target = oid(submission_id); row = submissions.find_one({"_id": target})
    if not row: raise HTTPException(404, "Submission not found")
    row = enrich_admin(row)
    if row.get("assessment_status") != "complete": raise HTTPException(409, "Automatic assessment is still incomplete")
    update = {"status": "approved", "approved_at": datetime.now(timezone.utc), "approved_by": user["sub"],
              "updated_at": datetime.now(timezone.utc)}
    assessments.update_one({"submission_id": target}, {"$set": update}); row.update(update)
    return serialize(row)


@app.post("/api/admin/submissions/{submission_id}/feedback", response_model=AdminDetail)
def save_feedback(submission_id: str, payload: AdminFeedbackInput, user=Depends(admin_only)):
    """Append human feedback without automatically changing scoring weights or approval state."""
    target = oid(submission_id); row = submissions.find_one({"_id": target})
    if not row: raise HTTPException(404, "Submission not found")
    row = enrich_admin(row)
    valid_codes = {factor["code"] for factor in row.get("risk_factors", [])}
    if any(code not in valid_codes for code in payload.factor_codes):
        raise HTTPException(422, "Feedback contains an unknown risk factor")
    now = datetime.now(timezone.utc)
    feedback = payload.model_dump() | {"created_at": now, "updated_at": now, "admin_id": user["sub"]}
    assessments.update_one({"submission_id": target}, {"$push": {"admin_feedback": feedback},
                                               "$set": {"updated_at": now}})
    row.setdefault("admin_feedback", []).append(feedback)
    return serialize(enrich_admin(row))