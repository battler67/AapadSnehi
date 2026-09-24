from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, Float, Boolean, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..models import utcnow


class Identity(Base):
    __tablename__ = "flood_identities"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(160), default="*")
    team_id: Mapped[str | None] = mapped_column(ForeignKey("flood_teams.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "flood_teams"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(160), default="*")
    volunteer_ids: Mapped[str] = mapped_column(Text, default="[]")


class Place(Base):
    __tablename__ = "flood_places"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("flood_places.id"), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(Text)
    original: Mapped[str] = mapped_column(Text)


class Operation(Base):
    __tablename__ = "flood_operations"
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    place_id: Mapped[str | None] = mapped_column(ForeignKey("flood_places.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(160), index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    verification: Mapped[str] = mapped_column(String(30), default="unverified", index=True)
    urgency: Mapped[str] = mapped_column(String(20), default="review", index=True)
    urgency_reason: Mapped[str] = mapped_column(Text, default="Awaiting human review")
    canonical_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_people: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    merged_into: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ReportDetail(Base):
    __tablename__ = "flood_report_details"
    report_id: Mapped[int] = mapped_column(ForeignKey("citizen_reports.id"), primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    resolution: Mapped[str] = mapped_column(String(30), default="clarification", index=True)
    payload: Mapped[str] = mapped_column(Text)
    normalized_address: Mapped[str] = mapped_column(Text)
    places: Mapped[str] = mapped_column(Text, default="{}")


class Media(Base):
    __tablename__ = "flood_media"
    __table_args__ = (UniqueConstraint("report_id", "sha256"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("citizen_reports.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    original: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    derivative: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PhotoReview(Base):
    __tablename__ = "flood_photo_reviews"
    media_id: Mapped[str] = mapped_column(ForeignKey("flood_media.id"), primary_key=True)
    result: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RescueTask(Base):
    __tablename__ = "flood_rescue_tasks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("flood_teams.id"), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(30), default="needs_review", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str] = mapped_column(Text, default="")
    assisted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Audit(Base):
    __tablename__ = "flood_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
