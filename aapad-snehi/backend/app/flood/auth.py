import hashlib
from fastapi import Depends, Header, HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria
from ..database import get_db
from ..models import CitizenReport, Incident
from .models import Identity, Operation, ReportDetail, RescueTask


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@event.listens_for(Session, "do_orm_execute")
def isolate_legacy_routes(state):
    """Legacy unauthenticated workflows must never load protected operational rows."""
    if state.is_select and not state.session.info.get("flood_access"):
        state.statement = state.statement.options(
            with_loader_criteria(Incident, ~Incident.id.in_(select(Operation.incident_id)), include_aliases=True),
            with_loader_criteria(CitizenReport, ~CitizenReport.id.in_(select(ReportDetail.report_id)), include_aliases=True),
        )


def flood_db(db: Session = Depends(get_db)):
    db.info["flood_access"] = True
    return db


def actor(authorization: str = Header(""), db: Session = Depends(flood_db)):
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ")
    identity = db.scalar(select(Identity).where(Identity.token_hash == digest(token), Identity.enabled.is_(True)))
    if not identity:
        raise HTTPException(401, "Invalid or revoked operational credential")
    return identity


def authorize(identity, operation, db, coordinator=False):
    if not identity:
        raise HTTPException(401, "An operational credential is required")
    if identity.scope != "*" and identity.scope != operation.scope:
        raise HTTPException(403, "Incident is outside your authorized city scope")
    if coordinator and identity.role != "coordinator":
        raise HTTPException(403, "Coordinator permission required")
    if identity.role == "responder":
        assigned = db.scalar(select(RescueTask.id).where(RescueTask.incident_id == operation.incident_id, RescueTask.team_id == identity.team_id))
        if not identity.team_id or not assigned:
            raise HTTPException(403, "Incident is not assigned to your team")


def own_report(detail, token):
    if not token or digest(token) != detail.owner_hash:
        raise HTTPException(403, "The private reporter access key is required")
