from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .adapters.base import AdapterConfigurationError, AdapterError
from .adapters.bluesky import BlueskyAdapter
from .adapters.government import validate_government_url
from .allocation import (
    AllocationPlan,
    AllocationProblem,
    IncidentAllocationInput,
    VolunteerAllocationInput,
    get_strategy,
    strategy_metadata,
)
from .config import settings
from .database import get_db, initialize_database
from .models import (
    Assignment,
    CitizenReport,
    Incident,
    IngestionRun,
    Source,
    Volunteer,
)
from .priority import compute_priority, volunteer_fit
from .schemas import (
    AssignmentCreate,
    ClaimCreate,
    DistributionRequest,
    GovernmentSourceCreate,
    BlueskyScanRequest,
    IngestionRequest,
    ReportModerationUpdate,
    VolunteerCreate,
)
from .serializers import (
    assignment_dict,
    incident_dict,
    report_dict,
    run_dict,
    source_dict,
    volunteer_dict,
)

from .services.image_triage import (
    CaptionProviderError,
    InvalidImageError,
    OpenAIVisionCaptionClient,
    prepare_inference_image,
    triage_report_assessment,
    triage_storage_unavailable,
    triage_unavailable,
)
from .services.image_storage import CloudinaryImageStore, ImageStorageError, StoredImage
from .services.ingestion import run_ingestion
from .services.sachet_scheduler import run_sachet_poll_loop
from .edge.mqtt import mqtt_ingestion
from .edge.routes import router as edge_router
from .edge.simulator import simulation_manager
from .flood.routes import router as flood_router
from .ml.routes import router as ml_router


caption_client = OpenAIVisionCaptionClient(
    api_key=settings.openai_api_key,
    model=settings.openai_vision_model,
    timeout_seconds=settings.openai_timeout_seconds,
    max_calls_per_hour=settings.openai_max_calls_per_hour,
)
image_store = CloudinaryImageStore(
    connection_value=settings.cloudinary_key,
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    review_url_seconds=settings.cloudinary_review_url_seconds,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    mqtt_ingestion.start()
    poll_task: asyncio.Task[None] | None = None
    if settings.enable_live_adapters and settings.sachet_poll_seconds > 0:
        poll_task = asyncio.create_task(
            run_sachet_poll_loop(settings.sachet_poll_seconds),
            name="sachet-india-poller",
        )
    try:
        yield
    finally:
        await simulation_manager.shutdown()
        mqtt_ingestion.stop()
        if poll_task:
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task


app = FastAPI(
    title="AapadSnehi API",
    version="0.1.0",
    description="Trust-aware incident ingestion and volunteer coordination API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(edge_router)
app.include_router(flood_router)
app.include_router(ml_router)


@app.middleware("http")
async def private_flood_cache_policy(request, call_next):
    if request.url.path == "/api/v1/ml/predict":
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length) if raw_length else 0
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
        if content_length > settings.ml_max_payload_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Prediction payload exceeds the {settings.ml_max_payload_bytes}-byte limit"},
            )
    response = await call_next(request)
    if request.url.path.startswith("/api/flood"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Authorization, X-Reporter-Token"
    if request.url.path.startswith("/api/v1/ml"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
        values = parsed if isinstance(parsed, list) else raw.split(",")
    except json.JSONDecodeError:
        values = raw.split(",")
    return sorted({str(value).strip().lower() for value in values if str(value).strip()})


def _safe_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "government-feed"
    return f"{base}-{secrets.token_hex(3)}"


def _valid_image_suffix(content: bytes, media_type: str | None) -> str | None:
    if content.startswith(b"\xff\xd8\xff") and media_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n") and media_type == "image/png":
        return ".png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP" and media_type == "image/webp":
        return ".webp"
    return None


def _local_report_image(file_name: str) -> Path | None:
    if not file_name or Path(file_name).name != file_name:
        return None
    root = settings.upload_dir.resolve()
    candidate = (root / file_name).resolve()
    if candidate.parent != root:
        return None
    return candidate


def _refresh_incident_priority(incident: Incident) -> None:
    needs = _json_list(incident.needs_json)
    score, breakdown = compute_priority(
        severity=incident.severity,
        occurred_at=incident.occurred_at,
        affected_estimate=incident.affected_estimate,
        needs=needs,
        verification_status=incident.verification_status,
        response_coverage=incident.response_coverage,
    )
    incident.priority_score = score
    incident.priority_breakdown_json = json.dumps(breakdown)


def _allocation_plan_dict(
    plan: AllocationPlan,
    problem: AllocationProblem,
    *,
    committed: bool = False,
    assignments: list[Assignment] | None = None,
) -> dict:
    return {
        "previewToken": _allocation_plan_token(plan, problem),
        "strategy": {
            "key": plan.strategy_key,
            "name": plan.strategy_name,
            "version": plan.strategy_version,
        },
        "committed": committed,
        "summary": {
            "selectedVolunteers": len(plan.decisions) + len(plan.unassigned),
            "allocatedVolunteers": len(plan.decisions),
            "unassignedVolunteers": len(plan.unassigned),
            "coveredIncidents": len({item.incident_id for item in plan.decisions}),
        },
        "allocations": [
            {
                "incidentId": item.incident_id,
                "incidentTitle": item.incident_title,
                "incidentLocation": item.incident_location,
                "volunteerId": item.volunteer_id,
                "volunteerName": item.volunteer_name,
                "service": item.service,
                "fitScore": item.fit_score,
                "allocationScore": item.allocation_score,
                "breakdown": item.breakdown,
            }
            for item in plan.decisions
        ],
        "unassigned": [
            {
                "volunteerId": item.volunteer_id,
                "volunteerName": item.volunteer_name,
                "reason": item.reason,
            }
            for item in plan.unassigned
        ],
        "assignments": [assignment_dict(item) for item in assignments or []],
    }


def _allocation_plan_token(plan: AllocationPlan, problem: AllocationProblem) -> str:
    fingerprint = {
        "strategy": [plan.strategy_key, plan.strategy_version],
        "incidents": [
            [
                item.id,
                item.severity,
                item.priority_score,
                item.latitude,
                item.longitude,
                item.needs,
                item.existing_coverage,
            ]
            for item in problem.incidents
        ],
        "volunteers": [
            [
                item.id,
                item.availability,
                item.latitude,
                item.longitude,
                item.services,
                item.skills,
            ]
            for item in problem.volunteers
        ],
        "existingPairs": sorted(problem.existing_pairs),
        "decisions": [
            [
                item.incident_id,
                item.volunteer_id,
                item.service,
                item.fit_score,
                item.allocation_score,
                item.breakdown,
            ]
            for item in plan.decisions
        ],
        "unassigned": [
            [item.volunteer_id, item.reason]
            for item in plan.unassigned
        ],
    }
    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AapadSnehi API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.scalar(select(1))
    return {"status": "ok", "database": "connected"}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    incident_count = db.scalar(select(func.count(Incident.id)).where(Incident.is_active.is_(True))) or 0
    critical_count = db.scalar(
        select(func.count(Incident.id)).where(Incident.is_active.is_(True), Incident.severity >= 4)
    ) or 0
    available_count = db.scalar(
        select(func.count(Volunteer.id)).where(Volunteer.availability == "available")
    ) or 0
    active_assignment_count = db.scalar(
        select(func.count(Assignment.id)).where(Assignment.status.in_(["assigned", "accepted", "claimed"]))
    ) or 0
    latest_incidents = list(
        db.scalars(
            select(Incident)
            .where(Incident.is_active.is_(True))
            .order_by(Incident.priority_score.desc())
            .limit(6)
        ).all()
    )
    external_incidents = list(
        db.scalars(
            select(Incident)
            .join(Source)
            .where(
                Incident.is_active.is_(True),
                Source.adapter_type.in_(("serper", "google_news", "sachet", "bluesky")),
            )
            .order_by(Incident.priority_score.desc(), Incident.occurred_at.desc())
            .limit(5)
        ).all()
    )
    sources = list(db.scalars(select(Source).order_by(Source.id)).all())
    return {
        "mode": "live-enabled" if settings.enable_live_adapters else "demo-safe",
        "metrics": {
            "activeIncidents": incident_count,
            "highPriority": critical_count,
            "availableVolunteers": available_count,
            "activeAssignments": active_assignment_count,
        },
        "priorityIncidents": [incident_dict(item) for item in latest_incidents],
        "externalIncidents": [incident_dict(item) for item in external_incidents],
        "sources": [source_dict(item) for item in sources],
    }


@app.get("/api/incidents")
def list_incidents(
    days: int = Query(default=30, ge=1, le=365),
    disaster_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    since = _utcnow() - timedelta(days=days)
    query = select(Incident).where(
        Incident.is_active.is_(True),
        Incident.occurred_at >= since,
    )
    if disaster_type and disaster_type != "all":
        query = query.where(Incident.disaster_type == disaster_type)
    incidents = db.scalars(query.order_by(Incident.priority_score.desc())).unique().all()
    return [incident_dict(item) for item in incidents]


@app.get("/api/incidents/heatmap")
def incident_heatmap(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> list[dict]:
    since = _utcnow() - timedelta(days=days)
    incidents = db.scalars(
        select(Incident)
        .where(Incident.is_active.is_(True), Incident.occurred_at >= since)
        .order_by(Incident.priority_score.desc())
    ).all()
    return [
        {
            "id": item.id,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "weight": round(max(0.1, item.priority_score / 100), 2),
            "severity": item.severity,
            "disasterType": item.disaster_type,
            "verificationStatus": item.verification_status,
        }
        for item in incidents
    ]


@app.post("/api/reports", status_code=status.HTTP_201_CREATED)
async def create_report(

    db: Session = Depends(get_db),
    reporter_name: str = Form(...),
    contact: str = Form(...),
    description: str = Form(...),
    disaster_type: str = Form(...),
    severity: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    location_name: str = Form(...),
    needs: str = Form(...),
    consent: bool = Form(...),
    image: UploadFile = File(...),
) -> dict:
    if not consent:
        raise HTTPException(status_code=422, detail="Evidence-use consent is required")
    content = await image.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload limit")
    suffix = _valid_image_suffix(content, image.content_type)
    if suffix is None:
        raise HTTPException(status_code=415, detail="Only valid JPEG, PNG, or WebP images are accepted")

    tracking_id = f"AS-{_utcnow():%Y%m%d}-{secrets.token_hex(4).upper()}"
    caption_text = ""
    caption_model = ""
    caption_provider = ""
    caption_prompt_version = ""
    caption_analysis: dict[str, object] = {}
    prepared_image = None
    try:
        prepared_image = await asyncio.to_thread(
            prepare_inference_image,
            content,
            media_type=image.content_type or "application/octet-stream",
        )
    except InvalidImageError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except CaptionProviderError:
        triage = triage_unavailable()

    stored_image: StoredImage | None = None
    destination: Path | None = None
    image_storage_status = "cloudinary"
    try:
        stored_image = await image_store.upload(content, tracking_id=tracking_id)
    except ImageStorageError:
        image_storage_status = "local_fallback"
        file_name = f"{tracking_id.lower()}{suffix}"
        destination = settings.upload_dir / file_name
        destination.write_bytes(content)

    if prepared_image is not None:
        try:
            caption_result = await caption_client.caption(prepared_image)
            caption_text = caption_result.caption
            caption_model = caption_result.model
            caption_provider = caption_result.provider
            caption_prompt_version = caption_result.prompt_version
            caption_analysis = caption_result.analysis_dict()
            triage = triage_report_assessment(caption_result, disaster_type)
        except CaptionProviderError:
            triage = triage_unavailable()
    if triage.decision == "accepted" and stored_image is None:
        triage = triage_storage_unavailable()

    try:
        source = db.scalar(select(Source).where(Source.slug == "citizen-reports"))
        if source is None:
            source = Source(
                slug="citizen-reports",
                name="Citizen incident reports",
                adapter_type="citizen",
                authority="Community evidence queue",
                source_kind="community",
                status="healthy",
                enabled=True,
            )
            db.add(source)
            db.flush()

        safe_needs = _json_list(needs)
        occurred_at = _utcnow()
        verification_status = "ai_screened" if triage.decision == "accepted" else "unverified"
        normalized_disaster_type = (
            triage.inferred_hazard
            if triage.decision == "accepted" and triage.inferred_hazard != "other"
            else disaster_type.lower()
        )
        score, breakdown = compute_priority(
            severity=severity,
            occurred_at=occurred_at,
            affected_estimate=0,
            needs=safe_needs,
            verification_status=verification_status,
        )
        incident = Incident(
            source_id=source.id,
            external_id=tracking_id,
            title=f"Community report: {location_name}",
            description=description,
            disaster_type=normalized_disaster_type,
            severity=severity,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            occurred_at=occurred_at,
            source_kind="community",
            verification_status=verification_status,
            affected_estimate=0,
            needs_json=json.dumps(safe_needs),
            priority_score=score,
            priority_breakdown_json=json.dumps(breakdown),
            is_active=triage.decision == "accepted",
        )
        db.add(incident)
        db.flush()

        report = CitizenReport(
            tracking_id=tracking_id,
            incident_id=incident.id,
            reporter_name=reporter_name.strip() or "Anonymous",
            contact=contact.strip(),
            description=description,
            image_path=destination.name if destination else "",
            cloudinary_public_id=stored_image.public_id if stored_image else "",
            cloudinary_asset_id=stored_image.asset_id if stored_image else "",
            cloudinary_format=stored_image.format if stored_image else "",
            image_storage_status=image_storage_status,
            consent=True,
            moderation_status=triage.decision,
            ai_caption=caption_text,
            ai_decision=triage.decision,
            ai_reason=triage.reason,
            ai_model=caption_model,
            ai_provider=caption_provider,
            ai_prompt_version=caption_prompt_version,
            ai_analysis_json=json.dumps(caption_analysis),
        )
        db.add(report)
        db.commit()
    except Exception:
        db.rollback()
        if stored_image:
            with suppress(ImageStorageError):
                await image_store.delete(stored_image.public_id)
        if destination:
            with suppress(OSError):
                destination.unlink(missing_ok=True)
        raise
    db.refresh(incident)
    messages = {
        "accepted": "Disaster evidence detected. The community signal is now visible for response review.",
        "rejected": "A volunteer rejected this report.",
        "needs_volunteer_review": "The image needs volunteer approval before it can appear on the dashboard.",
    }
    return {
        "trackingId": tracking_id,
        "moderationStatus": triage.decision,
        "message": messages[triage.decision],
        "caption": caption_text,
        "triageReason": triage.reason,
        "incident": incident_dict(incident),
    }


@app.get("/api/reports")
def list_reports(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    reports = db.scalars(
        select(CitizenReport)
        .order_by(CitizenReport.created_at.desc())
        .limit(limit)
    ).unique().all()
    return [report_dict(report) for report in reports]


@app.get("/api/reports/{tracking_id}/image")
async def get_report_image(
    tracking_id: str,
    db: Session = Depends(get_db),
):
    report = db.scalar(
        select(CitizenReport).where(CitizenReport.tracking_id == tracking_id)
    )
    if (
        report is None
        or report.moderation_status == "rejected"
        or report.image_storage_status == "deleted"
    ):
        raise HTTPException(status_code=404, detail="Report image not found")
    if report.cloudinary_public_id:
        try:
            url = await image_store.temporary_url(
                report.cloudinary_public_id,
                report.cloudinary_format,
            )
        except ImageStorageError as exc:
            raise HTTPException(status_code=503, detail="Report image is temporarily unavailable") from exc
        return RedirectResponse(
            url=url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Cache-Control": "private, no-store"},
        )
    local_path = _local_report_image(report.image_path)
    if local_path is None or not local_path.is_file():
        raise HTTPException(status_code=404, detail="Report image not found")
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    media_type = media_types.get(local_path.suffix.lower())
    if media_type is None:
        raise HTTPException(status_code=404, detail="Report image not found")
    return FileResponse(
        local_path,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@app.patch("/api/reports/{tracking_id}/moderation")
async def moderate_report(
    tracking_id: str,
    payload: ReportModerationUpdate,
    db: Session = Depends(get_db),
) -> dict:
    report = db.scalar(
        select(CitizenReport).where(CitizenReport.tracking_id == tracking_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Citizen report not found")
    if report.moderation_status != "needs_volunteer_review":
        raise HTTPException(status_code=409, detail="This report is no longer waiting for review")
    incident = report.incident
    report.reviewed_by = payload.reviewer_name.strip()
    report.reviewed_at = _utcnow()
    if payload.decision == "approve":
        report.moderation_status = "community_approved"
        incident.is_active = True
        incident.verification_status = "community_reviewed"
    else:
        if report.cloudinary_public_id:
            try:
                await image_store.delete(report.cloudinary_public_id)
            except ImageStorageError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="The stored image could not be deleted, so rejection was not saved",
                ) from exc
        local_path = _local_report_image(report.image_path)
        if report.image_path and (local_path is None or not local_path.is_file()):
            raise HTTPException(
                status_code=502,
                detail="The stored image could not be deleted, so rejection was not saved",
            )
        if local_path:
            try:
                local_path.unlink()
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="The stored image could not be deleted, so rejection was not saved",
                ) from exc
        report.cloudinary_public_id = ""
        report.cloudinary_asset_id = ""
        report.cloudinary_format = ""
        report.image_path = ""
        report.image_storage_status = "deleted"
        report.moderation_status = "rejected"
        incident.is_active = False
        incident.verification_status = "unverified"
    _refresh_incident_priority(incident)
    db.commit()
    db.refresh(report)
    return report_dict(report)


@app.get("/api/volunteers")
def list_volunteers(db: Session = Depends(get_db)) -> list[dict]:
    volunteers = db.scalars(select(Volunteer).order_by(Volunteer.verified.desc(), Volunteer.name)).all()
    return [volunteer_dict(item) for item in volunteers]


@app.post("/api/volunteers", status_code=status.HTTP_201_CREATED)
def create_volunteer(
    payload: VolunteerCreate,
    db: Session = Depends(get_db),
) -> dict:
    volunteer = Volunteer(
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        email=payload.email.strip(),
        home_location=payload.home_location.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        services_json=json.dumps(payload.services),
        skills_json=json.dumps(payload.skills),
        languages_json=json.dumps(payload.languages),
        preferred_places_json=json.dumps(payload.preferred_places),
        availability=payload.availability,
        verified=False,
    )
    db.add(volunteer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A volunteer with this phone already exists") from exc
    db.refresh(volunteer)
    return volunteer_dict(volunteer)


@app.get("/api/tasks/open")
def open_tasks(db: Session = Depends(get_db)) -> list[dict]:
    since = _utcnow() - timedelta(days=30)
    incidents = db.scalars(
        select(Incident)
        .where(Incident.is_active.is_(True), Incident.occurred_at >= since)
        .order_by(Incident.priority_score.desc())
    ).all()
    return [incident_dict(item) for item in incidents]


@app.post("/api/tasks/{incident_id}/claim", status_code=status.HTTP_201_CREATED)
def claim_task(
    incident_id: int,
    payload: ClaimCreate,
    db: Session = Depends(get_db),
) -> dict:
    incident = db.get(Incident, incident_id)
    volunteer = db.get(Volunteer, payload.volunteer_id)
    if not incident or not incident.is_active:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    services = _json_list(volunteer.services_json)
    if payload.service.lower() not in services:
        raise HTTPException(status_code=422, detail="Volunteer is not registered for this service")
    assignment = Assignment(
        incident_id=incident.id,
        volunteer_id=volunteer.id,
        service=payload.service.lower(),
        status="claimed",
        assigned_by="Volunteer self-claim",
        accepted_at=_utcnow(),
    )
    db.add(assignment)
    incident.response_coverage += 1
    _refresh_incident_priority(incident)
    volunteer.availability = "limited"
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This volunteer already has this incident") from exc
    db.refresh(assignment)
    return assignment_dict(assignment)


@app.get("/api/assignments")
def list_assignments(db: Session = Depends(get_db)) -> list[dict]:
    assignments = db.scalars(select(Assignment).order_by(Assignment.assigned_at.desc())).all()
    return [assignment_dict(item) for item in assignments]


@app.get("/api/allocation-strategies")
def list_allocation_strategies() -> list[dict[str, str]]:
    return strategy_metadata()


@app.post("/api/allocations/distribute")
def distribute_volunteers(
    payload: DistributionRequest,
    db: Session = Depends(get_db),
) -> dict:

    try:
        strategy = get_strategy(payload.strategy)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc.args[0])) from exc
    incidents = db.scalars(select(Incident).where(Incident.id.in_(payload.incident_ids))).all()
    incident_lookup = {incident.id: incident for incident in incidents}
    missing_incidents = [item for item in payload.incident_ids if item not in incident_lookup]
    if missing_incidents:
        raise HTTPException(
            status_code=404,
            detail=f"Incident IDs not found: {missing_incidents}",
        )
    inactive_incidents = [incident.id for incident in incidents if not incident.is_active]
    if inactive_incidents:
        raise HTTPException(
            status_code=422,
            detail=f"Inactive incidents cannot receive volunteers: {inactive_incidents}",
        )

    volunteers = db.scalars(select(Volunteer).where(Volunteer.id.in_(payload.volunteer_ids))).all()
    volunteer_lookup = {volunteer.id: volunteer for volunteer in volunteers}
    missing_volunteers = [item for item in payload.volunteer_ids if item not in volunteer_lookup]
    if missing_volunteers:
        raise HTTPException(
            status_code=404,
            detail=f"Volunteer IDs not found: {missing_volunteers}",
        )

    existing_pairs = frozenset(
        (incident_id, volunteer_id)
        for incident_id, volunteer_id in db.execute(
            select(Assignment.incident_id, Assignment.volunteer_id).where(
                Assignment.incident_id.in_(payload.incident_ids),
                Assignment.volunteer_id.in_(payload.volunteer_ids),
            )
        ).all()
    )
    problem = AllocationProblem(
        incidents=tuple(
            IncidentAllocationInput(
                id=incident.id,
                title=incident.title,
                location_name=incident.location_name,
                severity=incident.severity,
                priority_score=incident.priority_score,
                latitude=incident.latitude,
                longitude=incident.longitude,
                needs=tuple(_json_list(incident.needs_json)),
                existing_coverage=incident.response_coverage,
            )
            for incident_id in payload.incident_ids
            if (incident := incident_lookup.get(incident_id)) is not None
        ),
        volunteers=tuple(
            VolunteerAllocationInput(
                id=volunteer.id,
                name=volunteer.name,
                availability=volunteer.availability,
                latitude=volunteer.latitude,
                longitude=volunteer.longitude,
                services=tuple(_json_list(volunteer.services_json)),
                skills=tuple(_json_list(volunteer.skills_json)),
            )
            for volunteer_id in payload.volunteer_ids
            if (volunteer := volunteer_lookup.get(volunteer_id)) is not None
        ),
        existing_pairs=existing_pairs,
    )
    plan = strategy.allocate(problem)
    if not payload.commit:
        return _allocation_plan_dict(plan, problem)
    preview_token = _allocation_plan_token(plan, problem)
    if not payload.preview_token or not secrets.compare_digest(payload.preview_token, preview_token):
        raise HTTPException(
            status_code=409,
            detail="The distribution changed after preview; generate and review a fresh plan",
        )
    if not plan.decisions:
        raise HTTPException(
            status_code=422,
            detail="The selected volunteers have no safe compatible allocations",
        )

    created: list[Assignment] = []
    incident_additions: dict[int, int] = {}
    for decision in plan.decisions:
        assignment = Assignment(
            incident_id=decision.incident_id,
            volunteer_id=decision.volunteer_id,
            service=decision.service,
            note=payload.note.strip(),
            status="assigned",
            assigned_by=f"Automated distribution: {plan.strategy_key}",
        )
        db.add(assignment)
        created.append(assignment)
        incident_additions[decision.incident_id] = (
            incident_additions.get(decision.incident_id, 0) + 1
        )
        volunteer_lookup[decision.volunteer_id].availability = "limited"

    for incident_id, addition in incident_additions.items():
        incident = incident_lookup[incident_id]
        incident.response_coverage += addition
        _refresh_incident_priority(incident)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The distribution changed before confirmation; generate a fresh preview",
        ) from exc
    for assignment in created:
        db.refresh(assignment)
    return _allocation_plan_dict(plan, problem, committed=True, assignments=created)


@app.post("/api/assignments", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
) -> dict:
    incident = db.get(Incident, payload.incident_id)
    volunteer = db.get(Volunteer, payload.volunteer_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    if volunteer.availability == "unavailable":
        raise HTTPException(status_code=422, detail="Volunteer is currently unavailable")
    assignment = Assignment(
        incident_id=incident.id,
        volunteer_id=volunteer.id,
        service=payload.service.lower(),
        note=payload.note.strip(),
        assigned_by="Demo administrator",
    )
    db.add(assignment)
    incident.response_coverage += 1
    _refresh_incident_priority(incident)
    volunteer.availability = "limited"
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This volunteer is already assigned here") from exc
    db.refresh(assignment)
    return assignment_dict(assignment)


@app.get("/api/incidents/{incident_id}/suggestions")
def volunteer_suggestions(incident_id: int, db: Session = Depends(get_db)) -> list[dict]:
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    needs = _json_list(incident.needs_json)
    volunteers = db.scalars(
        select(Volunteer).where(Volunteer.availability != "unavailable")
    ).all()
    suggestions = []
    for volunteer in volunteers:
        score, breakdown = volunteer_fit(
            incident_needs=needs,
            incident_severity=incident.severity,
            incident_latitude=incident.latitude,
            incident_longitude=incident.longitude,
            services=_json_list(volunteer.services_json),
            skills=_json_list(volunteer.skills_json),
            availability=volunteer.availability,
            volunteer_latitude=volunteer.latitude,
            volunteer_longitude=volunteer.longitude,
        )
        suggestions.append({**volunteer_dict(volunteer), "fitScore": score, "fitBreakdown": breakdown})
    return sorted(suggestions, key=lambda item: item["fitScore"], reverse=True)


@app.get("/api/sources")
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    return [source_dict(item) for item in db.scalars(select(Source).order_by(Source.id)).all()]


@app.post("/api/bluesky/scan")
async def scan_bluesky_authors(
    payload: BlueskyScanRequest,
    db: Session = Depends(get_db),
) -> dict:
    if not settings.enable_live_adapters:
        raise HTTPException(
            status_code=403,
            detail="Live adapters are disabled. Set AAPAD_ENABLE_LIVE_ADAPTERS=true.",
        )
    source = db.scalar(select(Source).where(Source.adapter_type == "bluesky"))
    if not source or not source.enabled:
        raise HTTPException(status_code=404, detail="Bluesky adapter source is unavailable")

    try:
        result = await BlueskyAdapter().scan_authors(payload.query)
    except AdapterConfigurationError as exc:
        source.status = "needs_config"
        source.last_error = str(exc)[:1000]
        source.last_run_at = _utcnow()
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AdapterError as exc:
        source.status = "degraded"
        source.last_error = str(exc)[:1000]
        source.last_run_at = _utcnow()
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    source.status = "healthy"
    source.last_error = ""
    source.last_run_at = _utcnow()
    db.commit()
    return result.as_dict()


@app.post("/api/sources/government", status_code=status.HTTP_201_CREATED)
def add_government_source(
    payload: GovernmentSourceCreate,
    db: Session = Depends(get_db),
) -> dict:
    endpoint = validate_government_url(str(payload.endpoint))
    source = Source(
        slug=_safe_slug(payload.name),
        name=payload.name.strip(),
        adapter_type="government",
        endpoint=endpoint,
        authority=payload.authority.strip(),
        source_kind="official",
        enabled=payload.enabled,
        status="ready",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source_dict(source)


@app.post("/api/ingestion/run")
async def ingest(
    payload: IngestionRequest,
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        runs = await run_ingestion(db, source_ids=payload.source_ids, live=payload.live)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [run_dict(item) for item in runs]


@app.get("/api/ingestion/runs")
def ingestion_runs(db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(30)).all()
    return [run_dict(item) for item in runs]
