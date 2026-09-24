import json
import math
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from ..models import CitizenReport, Incident, Source, utcnow
from .auth import digest
from .models import Audit, Media, Operation, Place, ReportDetail, RescueTask
from .photo_review import review_view


def normalized(value):
    return " ".join(value.split()).casefold()


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def stale(detail):
    hours = max(1, min(168, int(os.getenv("AAPAD_FLOOD_STALE_HOURS", "6"))))
    return detail.observed_at is None or detail.observed_at.replace(tzinfo=timezone.utc) < utcnow() - timedelta(hours=hours)


def audit(db, incident_id, identity, action, details):
    db.add(Audit(incident_id=incident_id, actor=identity.id if identity else "reporter", role=identity.role if identity else "citizen", action=action, details=json.dumps(details)))


def lock_operation(db, op, version):
    result = db.execute(update(Operation).where(Operation.incident_id == op.incident_id, Operation.version == version).values(version=version + 1))
    if result.rowcount != 1:
        raise HTTPException(409, "Incident changed. Refresh and review before retrying.")


def places_for(db, address):
    a = {k: normalized(v) for k, v in address.items()}
    result = {}
    parent = None
    definitions = [
        ("locality", ["state", "city", "locality", "ward"], address["locality"] or address["ward"]),
        ("street", ["state", "city", "locality", "ward", "street", "street_number"], address["street"]),
        ("building", ["state", "city", "locality", "ward", "street", "street_number", "building"] + ([] if a["building"] else ["door"]), address["building"] or address["door"]),
        ("landmark", ["state", "city", "locality", "ward", "landmark"], address["landmark"]),
    ]
    for kind, keys, label in definitions:
        # A door without street/locality cannot establish a stable building identity.
        if not label.strip() or not (a["locality"] or a["ward"]) or (kind == "building" and not a["street"]):
            continue
        key = digest(kind + json.dumps([a[k] for k in keys]))
        if not db.get(Place, key):
            db.add(Place(id=key, kind=kind, parent_id=parent if kind != "landmark" else result.get("locality"), display_name=label, original=json.dumps({k: address[k] for k in keys}), normalized=json.dumps({k: a[k] for k in keys})))
            db.flush()
        result[kind] = key
        if kind != "landmark":
            parent = key
    return result, a


def new_operation(db, payload, demo=False):
    source = db.scalar(select(Source).where(Source.slug == "citizen-flood-protected"))
    if not source:
        source = Source(slug="citizen-flood-protected", name="Citizen flood observations", adapter_type="citizen", source_kind="community", enabled=False)
        db.add(source)
        db.flush()
    incident = Incident(source_id=source.id, external_id=str(uuid.uuid4()), title="Citizen flood report", description="Protected citizen observation", disaster_type="flood", severity=1, latitude=None, longitude=None, location_name=payload["address"]["locality"], occurred_at=utcnow(), source_kind="community", verification_status="unverified", is_active=False)
    db.add(incident)
    db.flush()
    op = Operation(incident_id=incident.id, scope=normalized(payload["address"]["city"]), demo=demo,
                   urgency="high" if payload["kind"] == "rescue" else "review",
                   urgency_reason="Unverified rescue request: immediate human review" if payload["kind"] == "rescue" else "Awaiting human review")
    db.add(op)
    db.flush()
    return op


def create_report(db, submission, demo=False):
    payload = submission.model_dump(mode="json", exclude={"reporter_token", "idempotency_key"})
    fingerprint = digest(json.dumps(payload, sort_keys=True))
    old = db.scalar(select(ReportDetail).where(ReportDetail.idempotency_key == submission.idempotency_key))
    if old:
        if old.owner_hash != digest(submission.reporter_token) or old.payload_hash != fingerprint:
            raise HTTPException(409, "Idempotency key already used with different contents or access key")
        return old, False
    # Citizen updates are review candidates; ownership is required for direct association.
    op = None
    if submission.update_incident_id:
        op = db.get(Operation, submission.update_incident_id)
        owned = db.scalar(select(ReportDetail).where(ReportDetail.incident_id == submission.update_incident_id, ReportDetail.owner_hash == digest(submission.reporter_token)))
        if not op or not owned or op.merged_into or op.demo != demo:
            raise HTTPException(403, "To update this incident use its reporter access key; otherwise submit a new observation for review")
        lock_operation(db, op, op.version)
    if op is None:
        op = new_operation(db, payload, demo)
    report = CitizenReport(tracking_id="FL-" + uuid.uuid4().hex[:16].upper(), incident_id=op.incident_id, description="Protected flood observation", moderation_status="flood_review")
    db.add(report)
    db.flush()
    places, address = places_for(db, payload["address"])
    location = submission.location
    detail = ReportDetail(report_id=report.id, incident_id=op.incident_id, owner_hash=digest(submission.reporter_token), idempotency_key=submission.idempotency_key,
                          payload_hash=fingerprint, kind=submission.kind, observed_at=submission.observed_at,
                          latitude=location.latitude, longitude=location.longitude,
                          resolution="confirmed" if location.confirmed else "clarification", payload=json.dumps(payload), normalized_address=json.dumps(address), places=json.dumps(places))
    db.add(detail)
    if op.place_id is None:
        op.place_id = places.get("building") or places.get("street") or places.get("locality")
    needs_rescue = submission.kind == "rescue" or submission.kind == "update" and (bool(submission.people) or bool(submission.assistance))
    if needs_rescue and not db.scalar(select(RescueTask.id).where(RescueTask.incident_id == op.incident_id)):
        db.add(RescueTask(id=str(uuid.uuid4()), incident_id=op.incident_id))
    audit(db, op.incident_id, None, "citizen_observation", {"reportId": report.id, "observedAt": payload["observed_at"], "suggestedIncidentId": submission.update_incident_id})
    db.flush()
    return detail, True


def receipt(db, detail):
    report = db.get(CitizenReport, detail.report_id)
    op = db.get(Operation, detail.incident_id)
    return {"reference": report.tracking_id, "reportId": detail.report_id, "incidentId": detail.incident_id, "receivedAt": stamp(detail.received_at), "reviewStatus": op.verification, "locationStatus": detail.resolution,
            "media": [{"id": m.id, "review": review_view(db, m.id)} for m in db.scalars(select(Media).where(Media.report_id == detail.report_id))],
            "mediaCount": len(db.scalars(select(Media.id).where(Media.report_id == detail.report_id)).all()), "message": "Received by the platform. Submission does not mean a team has been dispatched."}


def task_dict(task):
    return {"id": task.id, "incidentId": task.incident_id, "teamId": task.team_id, "state": task.state, "version": task.version,
            "outcome": task.outcome, "assisted": task.assisted, "remaining": task.remaining, "updatedAt": stamp(task.updated_at)}


def records(db, op):
    return list(db.scalars(select(ReportDetail).where(ReportDetail.incident_id == op.incident_id).order_by(ReportDetail.received_at.desc(), ReportDetail.report_id.desc())))


def incident_view(db, op, private=False):
    reports = records(db, op)
    if not reports:
        result = {"id": op.incident_id, "version": op.version, "demo": op.demo, "mergedInto": op.merged_into, "status": op.status, "verification": op.verification, "urgency": op.urgency,
                  "point": None, "precision": "unknown", "locationStatus": "clarification", "city": "", "locality": "Reports moved — review retained tasks", "ward": "", "street": "", "types": [], "reportCount": 0,
                  "lastObservation": None, "stale": True, "conflict": False, "reviewNeeded": True, "waterLevel": "unknown", "trend": "unknown", "access": "unknown", "assignmentStates": [], "conditionBasis": "No remaining observations"}
        if private:
            result.update({"reports": [], "places": {}, "reportedPeople": None, "confirmedPeople": None,
                           "tasks": [task_dict(t) for t in db.scalars(select(RescueTask).where(RescueTask.incident_id == op.incident_id))],
                           "timeline": [{"id": a.id, "actor": a.actor, "role": a.role, "action": a.action, "at": stamp(a.created_at), "details": json.loads(a.details)} for a in db.scalars(select(Audit).where(Audit.incident_id == op.incident_id).order_by(Audit.id))]})
        return result
    canonical = next((r for r in reports if r.report_id == op.canonical_report_id), None)
    representative = canonical or reports[0]
    p = json.loads(representative.payload)
    observations = [r.observed_at for r in reports if r.observed_at]
    tasks = db.scalars(select(RescueTask).where(RescueTask.incident_id == op.incident_id)).all()
    counts = {(json.loads(r.payload)["people"], json.loads(r.payload)["count_quality"]) for r in reports}
    conflict = len(counts) > 1
    loc = p["location"]
    point = None
    if representative.resolution == "confirmed" and representative.latitude is not None:
        if private:
            point = [representative.latitude, representative.longitude]
        else:
            point = [(math.floor(representative.latitude / .02) + .5) * .02, (math.floor(representative.longitude / .02) + .5) * .02]
    result = {"id": op.incident_id, "version": op.version, "demo": op.demo, "status": op.status, "verification": op.verification, "urgency": op.urgency,
              "locationStatus": representative.resolution, "point": point, "precision": loc["precision"] if private else "approximate 0.02 degree grid",
              "locality": p["address"]["locality"], "ward": p["address"]["ward"], "city": p["address"]["city"], "street": p["address"]["street"],
              "types": sorted(set(r.kind for r in reports)), "reportCount": len(reports), "lastObservation": stamp(max(observations)) if observations else None,
              "stale": all(stale(r) for r in reports), "conflict": conflict, "reviewNeeded": conflict or canonical is None or (canonical.report_id != reports[0].report_id),
              "waterLevel": p["water_level"], "trend": p["trend"], "access": p["access"], "conditionBasis": "reviewed citizen observation" if canonical else "unreviewed citizen observation",
              "assignmentStates": sorted(set(t.state for t in tasks)), "mergedInto": op.merged_into}
    if private:
        result.update({"urgencyReason": op.urgency_reason, "evidence": op.evidence, "address": p["address"], "location": loc, "reportedPeople": p["people"] if canonical else None,
                       "countQuality": p["count_quality"] if canonical else "unreviewed", "confirmedPeople": op.confirmed_people, "canonicalReportId": op.canonical_report_id,
                       "places": json.loads(representative.places), "tasks": [task_dict(t) for t in tasks],
                       "reports": [{"id": r.report_id, "reference": db.get(CitizenReport, r.report_id).tracking_id, "receivedAt": stamp(r.received_at), "locationStatus": r.resolution, **json.loads(r.payload),
                                    "media": [{"id": m.id, "public": m.public, "review": review_view(db, m.id)} for m in db.scalars(select(Media).where(Media.report_id == r.report_id))]} for r in reports],
                       "timeline": [{"id": a.id, "actor": a.actor, "role": a.role, "action": a.action, "at": stamp(a.created_at), "details": json.loads(a.details)} for a in db.scalars(select(Audit).where(Audit.incident_id == op.incident_id).order_by(Audit.id))]})
    return result


def distance(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    delta = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(b[1]-a[1])/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(delta)))


def summarize(db, operations, private=False):
    buildings, teams = set(), set()
    count_candidates = {}
    result = {"activeIncidents": 0, "buildingsReportingFlooding": 0, "openRescueRequests": 0, "reportedPeople": 0, "estimatedPeople": 0, "confirmedPeople": 0, "unknownOrUnreviewedCounts": 0,
              "assignedTeams": 0, "blockedAccessReports": 0, "unresolvedLocationReports": 0, "staleIncidents": 0, "reviewNeeded": 0, "lastObservation": None}
    for op in operations:
        view = incident_view(db, op, True)
        if "reports" not in view:
            continue
        reports = records(db, op)
        result["activeIncidents"] += op.status in {"active", "monitoring"}
        result["staleIncidents"] += view["stale"]
        result["reviewNeeded"] += view["reviewNeeded"]
        for r in reports:
            p = json.loads(r.payload)
            building = json.loads(r.places).get("building")
            if building and (r.kind == "flood" or p["water_level"] != "unknown"):
                buildings.add(building)
            result["unresolvedLocationReports"] += r.resolution != "confirmed"
            result["blockedAccessReports"] += p["access"] == "blocked" or r.kind == "blocked"
        active_tasks = [t for t in view["tasks"] if t["state"] not in {"resolved", "cancelled"}]
        result["openRescueRequests"] += bool(active_tasks)
        teams.update(t["teamId"] for t in active_tasks if t["teamId"])
        if active_tasks:
            # Multiple operational incidents can share a building. Until their
            # household identity is reviewed, do not sum duplicate place counts.
            building_key = view.get("places", {}).get("building")
            unit = normalized(view.get("address", {}).get("door", ""))
            count_key = (building_key + ":" + unit) if building_key else f"incident:{op.incident_id}"
            count_candidates.setdefault(count_key, []).append(view)
        last = view["lastObservation"]
        if last and (not result["lastObservation"] or last > result["lastObservation"]):
            result["lastObservation"] = last
    result["buildingsReportingFlooding"] = len(buildings)
    result["assignedTeams"] = len(teams)
    for candidates in count_candidates.values():
        if len(candidates) > 1 or candidates[0]["reportedPeople"] is None:
            result["unknownOrUnreviewedCounts"] += 1
            continue
        view = candidates[0]
        result["estimatedPeople" if view["countQuality"] == "estimated" else "reportedPeople"] += view["reportedPeople"]
        result["confirmedPeople"] += view["confirmedPeople"] or 0
    if not private:
        # Avoid household-level headcount inference in public filtered summaries.
        for key in ("reportedPeople", "estimatedPeople", "confirmedPeople", "unknownOrUnreviewedCounts"):
            result.pop(key)
    return result
