from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import get_adapter
from ..adapters.base import AdapterConfigurationError
from ..config import settings
from ..models import Incident, IngestionRun, Source
from ..priority import compute_priority
from ..schemas import IncidentCandidate


_INGESTION_LOCK = asyncio.Lock()


def _store_candidate(db: Session, source: Source, candidate: IncidentCandidate) -> bool:
    existing = db.scalar(
        select(Incident).where(
            Incident.source_id == source.id,
            Incident.external_id == candidate.external_id,
        )
    )
    score, breakdown = compute_priority(
        severity=candidate.severity,
        occurred_at=candidate.occurred_at,
        affected_estimate=candidate.affected_estimate,
        needs=candidate.needs,
        verification_status=candidate.verification_status,
        response_coverage=existing.response_coverage if existing else 0,
    )
    values = {
        "title": candidate.title,
        "description": candidate.description,
        "disaster_type": candidate.disaster_type,
        "severity": candidate.severity,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "location_name": candidate.location_name,
        "occurred_at": candidate.occurred_at,
        "updated_at": datetime.now(timezone.utc),
        "source_kind": candidate.source_kind,
        "verification_status": candidate.verification_status,
        "source_url": candidate.source_url,
        "affected_estimate": candidate.affected_estimate,
        "needs_json": json.dumps(candidate.needs),
        "priority_score": score,
        "priority_breakdown_json": json.dumps(breakdown),
        "is_active": True,
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return False
    db.add(
        Incident(
            source_id=source.id,
            external_id=candidate.external_id,
            **values,
        )
    )
    return True


async def run_ingestion(
    db: Session,
    *,
    source_ids: list[int] | None = None,
    live: bool = False,
) -> list[IngestionRun]:
    async with _INGESTION_LOCK:
        return await _run_ingestion(
            db,
            source_ids=source_ids,
            live=live,
        )


async def _run_ingestion(
    db: Session,
    *,
    source_ids: list[int] | None = None,
    live: bool = False,
) -> list[IngestionRun]:
    if live and not settings.enable_live_adapters:
        raise PermissionError(
            "Live adapters are disabled. Set AAPAD_ENABLE_LIVE_ADAPTERS=true after reviewing provider terms."
        )
    query = select(Source).where(Source.enabled.is_(True)).order_by(Source.id)
    if source_ids:
        query = query.where(Source.id.in_(source_ids))
    sources = list(db.scalars(query).all())
    completed_runs: list[IngestionRun] = []

    for source in sources:
        run = IngestionRun(source_id=source.id, status="running")
        db.add(run)
        db.flush()
        if source.adapter_type != "seed" and not live:
            run.status = "skipped"
            run.error = "Live ingestion disabled for this run"
            run.completed_at = datetime.now(timezone.utc)
            completed_runs.append(run)
            continue
        adapter_type = get_adapter(source.adapter_type)
        if not adapter_type:
            run.status = "failed"
            run.error = f"No adapter registered for '{source.adapter_type}'"
            run.completed_at = datetime.now(timezone.utc)
            source.status = "misconfigured"
            completed_runs.append(run)
            continue
        try:
            adapter = adapter_type()
            candidates = await adapter.fetch(source)
            run.fetched_count = len(candidates)
            if adapter.snapshot_mode:
                current_ids = {candidate.external_id for candidate in candidates}
                stale_query = select(Incident).where(Incident.source_id == source.id)
                if current_ids:
                    stale_query = stale_query.where(Incident.external_id.not_in(current_ids))
                for stale_incident in db.scalars(stale_query).all():
                    stale_incident.is_active = False
            for candidate in candidates:
                if _store_candidate(db, source, candidate):
                    run.accepted_count += 1
                else:
                    run.duplicate_count += 1
            run.status = "success"
            source.status = "healthy"
            source.last_error = ""
        except AdapterConfigurationError as exc:
            run.status = "needs_config"
            run.error = str(exc)
            source.status = "needs_config"
            source.last_error = str(exc)
        except Exception as exc:  # a provider failure must not stop other sources
            run.status = "failed"
            run.error = str(exc)[:1000]
            source.status = "degraded"
            source.last_error = str(exc)[:1000]
        source.last_run_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        completed_runs.append(run)

    db.commit()
    for run in completed_runs:
        db.refresh(run)
    return completed_runs
