import io
import json
import uuid
import hashlib
import os
import time
import httpx
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File, Response
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..models import CitizenReport, utcnow
from ..config import settings
from ..services.image_triage import prepare_inference_image, InvalidImageError
from .auth import actor, authorize, flood_db, own_report
from .models import Audit, Identity, Media, Operation, Place, ReportDetail, RescueTask, Team
from .schemas import Submission, Review, Transition, Relocate, Regroup, Merge
from .photo_review import review_view, save_review, screen_photo
from .service import audit, create_report, receipt, incident_view, records, summarize, lock_operation, task_dict, normalized, distance, new_operation

router = APIRouter(prefix="/api/flood", tags=["Citizen flood and rescue"])
_last_geocode = 0.0


def operation(db, incident_id):
    op = db.get(Operation, incident_id)
    if not op:
        raise HTTPException(404, "Incident not found")
    return op


def report_detail(db, report_id):
    report = db.get(ReportDetail, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/session")
def session(identity=Depends(actor)):
    return {"role": identity.role if identity else "public", "name": identity.name if identity else "Public", "teamId": identity.team_id if identity else None, "scope": identity.scope if identity else None}


@router.post("/reports", status_code=201)
def submit(payload: Submission, db=Depends(flood_db)):
    try:
        detail, created = create_report(db, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        detail, created = create_report(db, payload)
        db.commit()
    return {**receipt(db, detail), "duplicateRetry": not created}


@router.get("/reports/{report_id}")
def own(report_id: int, x_reporter_token: str = Header(""), db=Depends(flood_db)):
    detail = report_detail(db, report_id)
    own_report(detail, x_reporter_token)
    return {**receipt(db, detail), "observation": json.loads(detail.payload)}


@router.get("/receipt")
def lookup_receipt(reference: str = Query(min_length=5, max_length=40), x_reporter_token: str = Header(""), db=Depends(flood_db)):
    report = db.scalar(select(CitizenReport).where(CitizenReport.tracking_id == reference))
    if not report:
        raise HTTPException(404, "Report reference not found")
    detail = report_detail(db, report.id)
    own_report(detail, x_reporter_token)
    return {**receipt(db, detail), "observation": json.loads(detail.payload), "assignmentStates": list(db.scalars(select(RescueTask.state).where(RescueTask.incident_id == detail.incident_id)))}


@router.get("/incidents")
def incidents(
    demo: bool = False, private: bool = False, kind: str = "", status: str = "", verification: str = "", urgency: str = "",
    locality: str = "", street: str = "", assignment: str = "", assistance: str = "", stale: bool | None = None, resolution: str = "",
    since: datetime | None = None, place_id: str = "", bbox: str = "", group_by: str = "locality",
    near_lat: float | None = Query(None, ge=-90, le=90), near_lon: float | None = Query(None, ge=-180, le=180), radius: int = Query(500, ge=50, le=5000),
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db=Depends(flood_db), identity=Depends(actor),
):
    if private and not identity:
        raise HTTPException(401, "Operational credential required")
    if assistance and not private:
        raise HTTPException(403, "Assistance filters require operational access")
    if not private and (place_id or group_by in {"building", "landmark"} or near_lat is not None):
        raise HTTPException(403, "Building and landmark drill-down require operational access")
    if group_by not in {"locality", "street", "building", "landmark"}:
        raise HTTPException(422, "Invalid grouping")
    bounds = None
    if bbox:
        try:
            bounds = [float(v) for v in bbox.split(",")]
            if len(bounds) != 4 or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "bbox must be west,south,east,north")
    query = select(Operation).where(Operation.demo == demo, Operation.merged_into.is_(None))
    for value, column in [(status, Operation.status), (verification, Operation.verification), (urgency, Operation.urgency)]:
        if value:
            query = query.where(column == value)
    if private and identity.scope != "*":
        query = query.where(Operation.scope == identity.scope)
    if private and identity.role == "responder":
        query = query.where(Operation.incident_id.in_(select(RescueTask.incident_id).where(RescueTask.team_id == identity.team_id)))
    # Explicit cap: do not return silently incomplete operational statistics.
    ops = list(db.scalars(query.order_by(Operation.incident_id.desc()).limit(2001)))
    if len(ops) > 2000:
        raise HTTPException(422, "Narrow status, urgency or authorized scope; query exceeds 2000 incidents")
    selected, views = [], []
    groups = {}
    for op in ops:
        view = incident_view(db, op, private)
        if "types" not in view:
            continue
        if kind and kind not in view["types"] or locality and normalized(locality) not in normalized(view["locality"]) or street and normalized(street) not in normalized(view["street"]):
            continue
        if assignment and assignment not in view["assignmentStates"] or stale is not None and view["stale"] != stale:
            continue
        if resolution and not any(r.resolution == resolution for r in records(db, op)):
            continue
        if since and (not view["lastObservation"] or datetime.fromisoformat(view["lastObservation"]).timestamp() < since.timestamp()):
            continue
        if assistance and not any(assistance in r["assistance"] for r in view["reports"]):
            continue
        if place_id and place_id not in view.get("places", {}).values():
            continue
        point = view["point"]
        if bounds and (not point or not (bounds[0] <= point[1] <= bounds[2] and bounds[1] <= point[0] <= bounds[3])):
            continue
        if near_lat is not None:
            if near_lon is None:
                raise HTTPException(422, "Both landmark coordinates are required")
            if not point or distance([near_lat, near_lon], point) > radius:
                continue
        selected.append(op)
        views.append(view)
        if private:
            key = view["places"].get(group_by, "unresolved")
            place = db.get(Place, key) if key != "unresolved" else None
            label = place.display_name if place else "Unresolved grouping"
        else:
            label = " / ".join(filter(None, [view["city"], view["locality"], view["ward"], view["street"] if group_by == "street" else ""])) or "Unresolved locality"
            key = label
        groups.setdefault(key, {"label": label, "ops": []})["ops"].append(op)
    return {"items": views[offset:offset+limit], "total": len(views), "offset": offset, "limit": limit,
            "summary": summarize(db, selected, private), "groups": [{"id": key, "label": value["label"], "incidentIds": [o.incident_id for o in value["ops"]], "summary": summarize(db, value["ops"], private)} for key, value in groups.items()],
            "definitions": {"buildingsReportingFlooding": "Distinct normalized buildings, not households; repeated reports count once.", "reportedPeople": "Latest explicitly reviewed incident situation, exact citizen counts; excludes resolved/cancelled requests.", "estimatedPeople": "Reviewed citizen estimates, separate from exact and responder-confirmed counts.", "confirmedPeople": "Explicit responder-verified count; never inferred from photographs.", "blockedAccessReports": "Observations of blockage, not distinct blocked streets or verified routes.", "staleIncidents": "All observations old or unknown; administrative edits never refresh observation time.", "landmark": f"Textual landmark grouping; coordinate proximity searches use a {radius} metre straight-line radius, not an access route."}}


@router.get("/incidents/{incident_id}")
def detail(incident_id: int, private: bool = False, db=Depends(flood_db), identity=Depends(actor)):
    op = operation(db, incident_id)
    if private:
        authorize(identity, op, db)
    return incident_view(db, op, private)


@router.get("/reports/{report_id}/suggestions")
def suggestions(report_id: int, db=Depends(flood_db), identity=Depends(actor)):
    r = report_detail(db, report_id)
    op = operation(db, r.incident_id)
    authorize(identity, op, db, True)
    a = json.loads(r.normalized_address)
    candidates = []
    for other in db.scalars(select(Operation).where(Operation.incident_id != op.incident_id, Operation.demo == op.demo, Operation.scope == op.scope, Operation.status.in_(["active", "monitoring"]), Operation.merged_into.is_(None)).limit(1000)):
        for s in records(db, other):
            b = json.loads(s.normalized_address)
            reasons = []
            if a["locality"] and a["locality"] == b["locality"] and a["street"] and a["street"] == b["street"]:
                reasons.append("Matching locality and street")
                if a["door"] and a["door"] == b["door"]:
                    reasons.append("Matching door on the same street")
            if r.latitude is not None and s.latitude is not None:
                metres = distance([r.latitude, r.longitude], [s.latitude, s.longitude])
                uncertainty = max(json.loads(r.payload)["location"]["accuracy"] or 0, json.loads(s.payload)["location"]["accuracy"] or 0)
                if metres <= min(1000, max(100, uncertainty)):
                    reasons.append(f"Points {round(metres)} m apart; accuracy must be reviewed")
            if reasons and (not r.observed_at or not s.observed_at or abs((r.observed_at-s.observed_at).total_seconds()) <= 86400):
                candidates.append({"incidentId": other.incident_id, "reasons": reasons, "sameType": r.kind == s.kind, "warning": "Candidate only; nearby households must remain distinct"})
                break
    return {"items": candidates[:50]}


@router.patch("/incidents/{incident_id}/review")
def review(incident_id: int, payload: Review, db=Depends(flood_db), identity=Depends(actor)):
    op = operation(db, incident_id)
    authorize(identity, op, db, True)
    r = report_detail(db, payload.report_id)
    if r.incident_id != incident_id:
        raise HTTPException(422, "Canonical report must belong to this incident")
    if payload.verification == "corroborated":
        if len({x.owner_hash for x in records(db, op)}) < 2:
            raise HTTPException(422, "Corroboration needs observations from at least two reporter access identities and reviewed evidence")
    if payload.confirmed_people is not None and payload.verification != "responder_verified":
        raise HTTPException(422, "Confirmed counts require responder verification and supporting evidence")
    lock_operation(db, op, payload.version)
    op.canonical_report_id = r.report_id
    op.verification, op.urgency, op.urgency_reason = payload.verification, payload.urgency, payload.reason
    op.confirmed_people, op.evidence, op.status = payload.confirmed_people, payload.reason, payload.status
    op.place_id = json.loads(r.places).get("building") or json.loads(r.places).get("street") or json.loads(r.places).get("locality")
    audit(db, incident_id, identity, "reviewed_situation", payload.model_dump())
    db.commit()
    return incident_view(db, op, True)


@router.patch("/reports/{report_id}/location")
def relocate(report_id: int, payload: Relocate, x_reporter_token: str = Header(""), db=Depends(flood_db), identity=Depends(actor)):
    r = report_detail(db, report_id)
    op = operation(db, r.incident_id)
    if identity:
        authorize(identity, op, db, True)
    else:
        own_report(r, x_reporter_token)
    lock_operation(db, op, payload.version)
    p = json.loads(r.payload)
    old = p["location"]
    p["location"] = payload.location.model_dump()
    r.payload = json.dumps(p)
    r.latitude, r.longitude = payload.location.latitude, payload.location.longitude
    r.resolution = "confirmed" if payload.location.confirmed else "clarification"
    audit(db, op.incident_id, identity, "location_confirmed" if payload.location.confirmed else "clarification_requested", {"reportId": report_id, "before": old, "after": p["location"], "reason": payload.reason})
    db.commit()
    return receipt(db, r)


@router.post("/reports/{report_id}/regroup")
def regroup(report_id: int, payload: Regroup, db=Depends(flood_db), identity=Depends(actor)):
    r = report_detail(db, report_id)
    source = operation(db, r.incident_id)
    authorize(identity, source, db, True)
    target = operation(db, payload.target_incident_id) if payload.target_incident_id else new_operation(db, json.loads(r.payload), source.demo)
    authorize(identity, target, db, True)
    if target.incident_id == source.incident_id or target.demo != source.demo or target.merged_into:
        raise HTTPException(422, "Choose a distinct active grouping in the same dataset")
    lock_operation(db, source, payload.version)
    lock_operation(db, target, target.version)
    r.incident_id = target.incident_id
    db.get(CitizenReport, r.report_id).incident_id = target.incident_id
    source.canonical_report_id = None
    source.confirmed_people = None
    target.canonical_report_id = None
    target.confirmed_people = None
    if r.kind == "rescue" and not db.scalar(select(RescueTask.id).where(RescueTask.incident_id == target.incident_id)):
        db.add(RescueTask(id=str(uuid.uuid4()), incident_id=target.incident_id))
    details = {"reportId": r.report_id, "from": source.incident_id, "to": target.incident_id, "reason": payload.reason, "taskPolicy": "Existing assignments remain at their source incident; review and explicitly cancel or reassign them"}
    audit(db, source.incident_id, identity, "report_regrouped", details)
    audit(db, target.incident_id, identity, "report_regrouped", details)
    db.commit()
    return details


@router.post("/incidents/{incident_id}/merge")
def merge(incident_id: int, payload: Merge, db=Depends(flood_db), identity=Depends(actor)):
    source, target = operation(db, incident_id), operation(db, payload.target_incident_id)
    authorize(identity, source, db, True)
    authorize(identity, target, db, True)
    if source.incident_id == target.incident_id or source.demo != target.demo or source.merged_into or target.merged_into:
        raise HTTPException(422, "Invalid merge target")
    tasks = list(db.scalars(select(RescueTask).where(RescueTask.incident_id.in_([incident_id, target.incident_id]))))
    active = [t for t in tasks if t.state not in {"resolved", "cancelled"}]
    if len(active) > 1:
        raise HTTPException(409, "Conflicting open rescue tasks: explicitly resolve or cancel redundant tasks before merging")
    if tasks and not payload.acknowledge_tasks:
        raise HTTPException(409, "Acknowledge moving all task relationships and retaining their history")
    lock_operation(db, source, payload.version)
    lock_operation(db, target, payload.target_version)
    for r in records(db, source):
        r.incident_id = target.incident_id
        db.get(CitizenReport, r.report_id).incident_id = target.incident_id
    for t in tasks:
        if t.incident_id == incident_id:
            t.incident_id = target.incident_id
            t.version += 1
    source.status, source.merged_into = "merged", target.incident_id
    target.canonical_report_id, target.confirmed_people = None, None
    details = payload.model_dump()
    audit(db, incident_id, identity, "incident_merged", details)
    audit(db, target.incident_id, identity, "incident_merge_received", {**details, "sourceIncidentId": incident_id, "historyUrl": f"/api/flood/incidents/{incident_id}?private=true"})
    db.commit()
    return {"incidentId": target.incident_id, "message": "Reports and tasks retained; canonical situation needs review"}


@router.get("/teams")
def teams(db=Depends(flood_db), identity=Depends(actor)):
    if not identity:
        raise HTTPException(401, "Operational credential required")
    return {"items": [{"id": t.id, "name": t.name} for t in db.scalars(select(Team)) if (identity.scope == "*" or t.scope == identity.scope) and (identity.role == "coordinator" or t.id == identity.team_id)]}


@router.get("/tasks")
def tasks(db=Depends(flood_db), identity=Depends(actor), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    if not identity:
        raise HTTPException(401, "Operational credential required")
    query = select(RescueTask).join(Operation, Operation.incident_id == RescueTask.incident_id)
    if identity.scope != "*":
        query = query.where(Operation.scope == identity.scope)
    if identity.role == "responder":
        query = query.where(RescueTask.team_id == identity.team_id)
    return {"items": [task_dict(t) for t in db.scalars(query.order_by(RescueTask.updated_at.desc()).offset(offset).limit(limit))]}


@router.post("/incidents/{incident_id}/task", status_code=201)
def create_task(incident_id: int, payload: Regroup, db=Depends(flood_db), identity=Depends(actor)):
    op = operation(db, incident_id)
    authorize(identity, op, db, True)
    lock_operation(db, op, payload.version)
    if op.merged_into:
        raise HTTPException(422, "Create the task on the merged target")
    if db.scalar(select(RescueTask.id).where(RescueTask.incident_id == incident_id, RescueTask.state.notin_(["resolved", "cancelled"]))):
        raise HTTPException(409, "An open rescue task already exists; review it before adding another")
    task = RescueTask(id=str(uuid.uuid4()), incident_id=incident_id)
    db.add(task)
    audit(db, incident_id, identity, "rescue_task_created", {"taskId": task.id, "reason": payload.reason})
    db.commit()
    return task_dict(task)


ALLOWED = {"needs_review": {"ready", "cancelled"}, "ready": {"assigned", "needs_review", "cancelled"}, "assigned": {"en_route", "ready", "cancelled", "assigned"},
           "en_route": {"on_scene", "unable_to_reach", "ready", "cancelled"}, "on_scene": {"resolved", "unable_to_reach", "ready"}, "unable_to_reach": {"ready", "en_route", "cancelled"}, "resolved": {"needs_review"}, "cancelled": {"needs_review"}}


@router.patch("/tasks/{task_id}")
def transition(task_id: str, payload: Transition, db=Depends(flood_db), identity=Depends(actor)):
    task = db.get(RescueTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    op = operation(db, task.incident_id)
    authorize(identity, op, db)
    if identity.role == "responder" and (task.team_id != identity.team_id or payload.state not in {"en_route", "on_scene", "resolved", "unable_to_reach"} or payload.team_id):
        raise HTTPException(403, "Responders may update progress only for their assigned task")
    if payload.state not in ALLOWED.get(task.state, set()):
        raise HTTPException(422, f"Transition {task.state} to {payload.state} is not allowed")
    if payload.state == "ready" and not op.canonical_report_id:
        raise HTTPException(422, "Review a canonical situation before marking ready")
    team_id = task.team_id
    if payload.state == "assigned":
        team = db.get(Team, payload.team_id or "")
        if not team or team.scope not in {"*", op.scope}:
            raise HTTPException(422, "Select a team authorized for this city")
        team_id = team.id
    elif payload.team_id:
        raise HTTPException(422, "Team changes require an assignment transition")
    if payload.state in {"ready", "needs_review"}:
        team_id = None
    if payload.state == "resolved" and (not payload.outcome.strip() or not payload.remaining.strip()):
        raise HTTPException(422, "Record an outcome and remaining needs (or explicitly none)")
    before = task_dict(task)
    # Lock the parent too, so task transitions cannot race a merge.
    lock_operation(db, op, op.version)
    result = db.execute(update(RescueTask).where(RescueTask.id == task_id, RescueTask.version == payload.version).values(state=payload.state, team_id=team_id, version=payload.version+1, outcome=payload.outcome, assisted=payload.assisted, remaining=payload.remaining, updated_at=utcnow()))
    if result.rowcount != 1:
        raise HTTPException(409, "Task changed. Refresh before assigning or updating it.")
    audit(db, op.incident_id, identity, "task_transition", {"taskId": task_id, "before": before, "after": payload.model_dump()})
    db.commit()
    db.refresh(task)
    return task_dict(task)


@router.post("/reports/{report_id}/media", status_code=201)
async def upload(report_id: int, image: UploadFile = File(...), x_reporter_token: str = Header(""), db=Depends(flood_db)):
    detail = report_detail(db, report_id)
    own_report(detail, x_reporter_token)
    content = await image.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Photo exceeds 8 MB. Your text report is already received.")
    try:
        derivative = prepare_inference_image(content, media_type=image.content_type or "")
    except InvalidImageError as exc:
        raise HTTPException(422, str(exc))
    photo_hash = hashlib.sha256(content).hexdigest()
    old = db.scalar(select(Media).where(Media.report_id == report_id, Media.sha256 == photo_hash))
    if old:
        return {"id": old.id, "attached": True, "public": old.public, "review": review_view(db, old.id)}
    op = operation(db, detail.incident_id)
    lock_operation(db, op, op.version)
    if len(db.scalars(select(Media.id).where(Media.report_id == report_id)).all()) >= 4:
        raise HTTPException(422, "Maximum four photos per report")
    media = Media(id=str(uuid.uuid4()), report_id=report_id, sha256=photo_hash, original=content, derivative=derivative.content, public=False)
    db.add(media)
    db.flush()
    save_review(db, media.id, {"status": "pending", "message": "Photo attached; AI screening pending. Human review still required."})
    audit(db, detail.incident_id, None, "photo_attached", {"reportId": report_id, "mediaId": media.id, "public": False})
    db.commit()
    # No database write lock is held across the external call. The report and photo
    # remain received even if screening times out or the client loses connectivity.
    result = await screen_photo(derivative)
    save_review(db, media.id, result)
    audit(db, detail.incident_id, None, "photo_ai_screened", {"mediaId": media.id, "status": result["status"], "advisoryOnly": True})
    db.commit()
    return {"id": media.id, "attached": True, "public": False, "review": result}


@router.get("/media/{media_id}")
def media_access(media_id: str, original: bool = False, x_reporter_token: str = Header(""), db=Depends(flood_db), identity=Depends(actor)):
    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(404, "Photo not found")
    detail = report_detail(db, media.report_id)
    if original or not media.public:
        if identity:
            authorize(identity, operation(db, detail.incident_id), db)
        else:
            own_report(detail, x_reporter_token)
    return Response(media.original if original else media.derivative, media_type="application/octet-stream" if original else "image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment" if original else "inline"})


@router.patch("/media/{media_id}/visibility")
def visibility(media_id: str, public: bool = False, x_reporter_token: str = Header(""), db=Depends(flood_db), identity=Depends(actor)):
    media = db.get(Media, media_id)
    if not media:
        raise HTTPException(404, "Photo not found")
    detail = report_detail(db, media.report_id)
    # Withholding is the supported privacy control. Publishing household imagery
    # needs a redaction workflow; never pretend metadata removal hides faces.
    if public:
        raise HTTPException(422, "Public photo publication is disabled; photographs remain private")
    if identity:
        authorize(identity, operation(db, detail.incident_id), db, True)
    else:
        own_report(detail, x_reporter_token)
    media.public = False
    audit(db, detail.incident_id, identity, "photo_withheld", {"mediaId": media_id})
    db.commit()
    return {"public": False}


@router.get("/geocode")
async def geocode(q: str = Query(min_length=3, max_length=200)):
    global _last_geocode
    user_agent = os.getenv("AAPAD_FLOOD_GEOCODER_USER_AGENT", "")
    if not settings.enable_live_adapters or not user_agent:
        raise HTTPException(503, "Address lookup is not configured. Enter the address and confirm a map pin, or submit for location clarification.")
    now = time.monotonic()
    if now - _last_geocode < 1.1:
        raise HTTPException(429, "Wait a moment before another address search")
    _last_geocode = now
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "addressdetails": 1, "limit": 5}, headers={"User-Agent": user_agent})
            response.raise_for_status()
            results = []
            for row in response.json()[:5]:
                lat, lon = float(row["lat"]), float(row["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                # Even an address result remains a suggestion. Broad matches
                # never acquire household precision from the query text.
                precision = "street" if row.get("addresstype") in {"road", "street"} else "locality"
                results.append({"label": str(row["display_name"])[:500], "location": {"latitude": lat, "longitude": lon, "source": "address_lookup", "accuracy": None, "confirmed": False, "precision": precision}})
            return {"items": results, "attribution": "© OpenStreetMap contributors", "message": "Suggested locations only. Correct and confirm where the photo was taken."}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Address provider unavailable. Use a manual pin or textual description.")
