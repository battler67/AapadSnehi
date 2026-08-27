from __future__ import annotations

import json
from typing import Any

from .models import Assignment, CitizenReport, Incident, IngestionRun, Source, Volunteer


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def incident_dict(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        "externalId": incident.external_id,
        "title": incident.title,
        "description": incident.description,
        "disasterType": incident.disaster_type,
        "severity": incident.severity,
        "intensity": "critical" if incident.severity >= 5 else "high" if incident.severity >= 4 else "medium" if incident.severity >= 3 else "low",
        "latitude": incident.latitude,
        "longitude": incident.longitude,
        "locationName": incident.location_name,
        "occurredAt": incident.occurred_at.isoformat(),
        "sourceKind": incident.source_kind,
        "verificationStatus": incident.verification_status,
        "sourceName": incident.source.name if incident.source else "Unknown source",
        "sourceAuthority": incident.source.authority if incident.source else "",
        "sourceUrl": incident.source_url,
        "affectedEstimate": incident.affected_estimate,
        "needs": _json_list(incident.needs_json),
        "priorityScore": incident.priority_score,
        "priorityBreakdown": _json_object(incident.priority_breakdown_json),
        "responseCoverage": incident.response_coverage,
        "assignmentCount": len(incident.assignments),
        "active": incident.is_active,
    }


def volunteer_dict(volunteer: Volunteer) -> dict[str, Any]:
    return {
        "id": volunteer.id,
        "name": volunteer.name,
        "phone": volunteer.phone,
        "email": volunteer.email,
        "homeLocation": volunteer.home_location,
        "latitude": volunteer.latitude,
        "longitude": volunteer.longitude,
        "services": _json_list(volunteer.services_json),
        "skills": _json_list(volunteer.skills_json),
        "languages": _json_list(volunteer.languages_json),
        "preferredPlaces": _json_list(volunteer.preferred_places_json),
        "availability": volunteer.availability,
        "verified": volunteer.verified,
        "completedMissions": volunteer.completed_missions,
    }


def report_dict(report: CitizenReport) -> dict[str, Any]:
    image_available = bool(report.cloudinary_public_id or report.image_path) and report.image_storage_status != "deleted"
    return {
        "id": report.id,
        "trackingId": report.tracking_id,
        "moderationStatus": report.moderation_status,
        "aiCaption": report.ai_caption,
        "aiDecision": report.ai_decision,
        "aiReason": report.ai_reason,
        "aiModel": report.ai_model,
        "aiProvider": report.ai_provider,
        "aiPromptVersion": report.ai_prompt_version,
        "aiAnalysis": _json_object(report.ai_analysis_json),
        "reviewedBy": report.reviewed_by,
        "reviewedAt": report.reviewed_at.isoformat() if report.reviewed_at else None,
        "createdAt": report.created_at.isoformat(),
        "imageAvailable": image_available,
        "imageUrl": f"/api/reports/{report.tracking_id}/image" if image_available else "",
        "incident": incident_dict(report.incident),
    }


def assignment_dict(assignment: Assignment) -> dict[str, Any]:
    return {
        "id": assignment.id,
        "incidentId": assignment.incident_id,
        "incidentTitle": assignment.incident.title if assignment.incident else "",
        "volunteerId": assignment.volunteer_id,
        "volunteerName": assignment.volunteer.name if assignment.volunteer else "",
        "service": assignment.service,
        "status": assignment.status,
        "note": assignment.note,
        "assignedBy": assignment.assigned_by,
        "assignedAt": assignment.assigned_at.isoformat(),
        "acceptedAt": assignment.accepted_at.isoformat() if assignment.accepted_at else None,
    }


def source_dict(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "slug": source.slug,
        "name": source.name,
        "adapterType": source.adapter_type,
        "endpoint": source.endpoint,
        "authority": source.authority,
        "sourceKind": source.source_kind,
        "enabled": source.enabled,
        "status": source.status,
        "lastRunAt": source.last_run_at.isoformat() if source.last_run_at else None,
        "lastError": source.last_error,
    }


def run_dict(run: IngestionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "sourceId": run.source_id,
        "sourceName": run.source.name if run.source else "Unknown source",
        "status": run.status,
        "fetchedCount": run.fetched_count,
        "acceptedCount": run.accepted_count,
        "duplicateCount": run.duplicate_count,
        "rejectedCount": run.rejected_count,
        "error": run.error,
        "startedAt": run.started_at.isoformat(),
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
    }
