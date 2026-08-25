"""
Purpose: Defines the FastAPI application lifecycle and role-protected vendor and
admin workflows, including automatic assessment, migration, and approval.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import Thread
from bson import ObjectId
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import login, require_role
from .database import assessments, initialize_database, submissions, upload_records
from .image_assessment import assess_submission_images
from .intelligence import build_intelligence, campaign_metadata, find_similar_submissions
from .llm_scoring import assess_with_local_llm, combine
from .schemas import AdminDetail, AdminFeedbackInput, AdminSummary, LoginInput, VendorInput, VendorReceipt, VendorSubmission
from .scoring import MANDATORY_SCORING_SERVICES, analyze_vendor
from .seed import seed_if_empty
from .uploads import resolve_upload, store_upload_batch


# Initializes MongoDB and demo data when the API starts.
@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(); seed_if_empty(); start_missing_score_recovery(); yield


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
    risk_reasons = [factor["reason"] for factor in ai.get("risk_factors", []) if factor.get("points", 0) > 0]
    trust_reduction = round(10 - (combined.get("trust_score") or 0), 1) if ai["status"] == "complete" else None
    score_explanation = {
        "spam": {"source_probability": ai.get("spam_probability"), "calculation": "spam_probability / 10",
                 "final_score": combined.get("spam_score"), "reasons": risk_reasons,
                 "explanation": "Spam Score is the local model's spam probability converted from 0-100 to 0-10."},
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


# ---------------------------------------------------------------------------
# IMPORTANT FIX: scoring must never run inside a GET/read path.
#
# The old ensure_current_assessment() used to be called from every
# admin_submissions()/admin_detail() GET request, which silently re-ran the
# local LLM for any "stale" row on every single page load or refresh. With
# several stale rows in the collection, one GET request could trigger many
# sequential (or overlapping, if multiple GETs land close together) Ollama
# calls, producing exactly the ReadTimeout pile-up seen in the logs.
#
# Scoring is now only triggered by:
#   1. A new vendor submission (background task, one submission at a time).
#   2. An explicit admin-triggered migration endpoint (below), so it happens
#      once, on purpose, not implicitly on every read.
# ---------------------------------------------------------------------------

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
    now = datetime.now(timezone.utc)
    for result in image_results:
        upload_records.update_one({"submission_id": submission_id, "storage_name": result["storage_name"]},
                                  {"$set": {"assessment": result, "updated_at": now}})
    assessment = assessment_fields(payload, prior)
    complete_images = sum(item["status"] == "complete" for item in image_results)
    if image_results and complete_images != len(image_results) and assessment["assessment_status"] == "complete":
        assessment["assessment_status"] = "image_ai_unavailable"
    assessment.update(image_assessments=image_results, image_assessment_summary={
        "total": len(image_results), "complete": complete_images,
        "unavailable": len(image_results) - complete_images,
        "relevant": sum(item.get("relevance") == "relevant" for item in image_results),
        "irrelevant": sum(item.get("relevance") == "irrelevant" for item in image_results),
        "duplicates": sum(bool(item.get("duplicate")) for item in image_results),
        "spam": sum(item.get("spam_detected") is True for item in image_results),
    }, updated_at=now)
    assessments.update_one({"submission_id": submission_id}, {"$set": assessment,
                           "$setOnInsert": {"submission_id": submission_id, "status": "pending", "created_at": now,
                                            "admin_feedback": []}}, upsert=True)


# Retries persisted submissions whose earlier local-model call produced no score.
def recover_missing_scores() -> None:
    """Reassess scoreless records after Ollama and its configured models become available."""
    for submission_id in assessments.distinct("submission_id", {"$or": [{"trust_score": None}, {"spam_score": None}]}):
        try:
            assess_stored_submission(submission_id)
        except Exception as exc:
            print(f"[ASSESSMENT RECOVERY FAILURE] {submission_id}: {type(exc).__name__}")


# Starts missing-score recovery without delaying FastAPI startup on a slow CPU model.
def start_missing_score_recovery() -> None:
    """Launch one daemon worker for previously unavailable assessments."""
    Thread(target=recover_missing_scores, name="assessment-recovery", daemon=True).start()


# Re-scores exactly one stale/legacy record. Used only by the migration endpoint below,
# never by a GET read path.
def migrate_one(row: dict) -> None:
    """Upgrade a single legacy record to the current assessment version."""
    assess_stored_submission(row["_id"])


# Joins the three MongoDB collections into the unchanged admin API shape.
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
    return result


# Adds dynamic campaign and reviewer metadata to an admin-only record.
# NOTE: no longer calls the LLM. It only enriches whatever is already stored.
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


# Reports basic API and database mode metadata.
@app.get("/api/health")
def health(): return {"status": "ok", "mode": "demo", "database": "mongodb"}


# Authenticates a demo vendor or administrator account.
@app.post("/api/auth/login")
def authenticate(payload: LoginInput): return login(payload.username, payload.password)


# Stores one multipart submission, then schedules private assessment from MongoDB.
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


# Lists only submissions owned by the authenticated vendor.
@app.get("/api/vendor/submissions", response_model=list[VendorSubmission])
def vendor_submissions(user=Depends(vendor_only)):
    rows = []
    for submission in submissions.find({"vendor_id": user["sub"]}).sort("created_at", -1):
        workflow = assessments.find_one({"submission_id": submission["_id"]}, {"status": 1}) or {}
        row = dict(submission); row["status"] = workflow.get("status", "pending")
        rows.append(serialize(row))
    return rows


# Lists all automatically assessed submissions for administrators.
# FIX: pure read — no scoring, no Ollama calls. Fast and safe to poll/refresh.
@app.get("/api/admin/submissions", response_model=list[AdminSummary])
def admin_submissions(user=Depends(admin_only)):
    """Expose internal scores only through the administrator-protected collection view."""
    return [serialize(enrich_admin(x)) for x in submissions.find().sort("created_at", -1)]


# Returns a full admin-only assessment and evidence breakdown.
# FIX: pure read — no scoring, no Ollama calls.
@app.get("/api/admin/submissions/{submission_id}", response_model=AdminDetail)
def admin_detail(submission_id: str, user=Depends(admin_only)):
    """Return the complete evidence ledger for human review."""
    row = submissions.find_one({"_id": oid(submission_id)})
    if not row: raise HTTPException(404, "Submission not found")
    return serialize(enrich_admin(row))


# NEW: explicit, admin-triggered migration. Re-scores only rows that are stale
# (old assessment_version or missing intelligence). This is the ONLY place
# besides new-submission background tasks where the LLM gets called for
# existing records — never implicitly from a GET.
@app.post("/api/admin/migrate")
def migrate_stale(user=Depends(admin_only)):
    """Re-score legacy records on demand instead of silently on every read."""
    current_ids = set(assessments.distinct("submission_id", {"assessment_version": "ai-image-v3"}))
    stale = list(submissions.find({"_id": {"$nin": list(current_ids)}}))
    for row in stale:
        migrate_one(row)
    return {"status": "ok", "migrated": len(stale)}


# Streams a stored submission upload only to authenticated administrators.
@app.get("/api/admin/uploads/{storage_name}")
def admin_upload(storage_name: str, user=Depends(admin_only)):
    """Protect service images and documents from unauthenticated public access."""
    metadata = upload_records.find_one({"storage_name": storage_name, "linked": True})
    if not metadata: raise HTTPException(404, "Upload is not linked to a submission")
    return FileResponse(resolve_upload(storage_name), media_type=metadata["content_type"], filename=metadata["original_name"])


# Records a human approval after automatic assessment completes.
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
    now = datetime.now(timezone.utc)
    feedback = payload.model_dump() | {"created_at": now, "updated_at": now, "admin_id": user["sub"]}
    assessments.update_one({"submission_id": target}, {"$push": {"admin_feedback": feedback},
                                               "$set": {"updated_at": now}})
    row.setdefault("admin_feedback", []).append(feedback)
    return serialize(enrich_admin(row))
