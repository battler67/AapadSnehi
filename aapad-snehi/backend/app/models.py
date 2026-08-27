from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    adapter_type: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(Text, default="")
    authority: Mapped[str] = mapped_column(String(180), default="")
    source_kind: Mapped[str] = mapped_column(String(30), default="official")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="ready")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incidents: Mapped[list[Incident]] = relationship(back_populates="source")
    runs: Mapped[list[IngestionRun]] = relationship(back_populates="source")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_incident_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(220), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    disaster_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[int] = mapped_column(Integer, default=1, index=True)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    location_name: Mapped[str] = mapped_column(String(180), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_kind: Mapped[str] = mapped_column(String(30), index=True)
    verification_status: Mapped[str] = mapped_column(String(30), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    affected_estimate: Mapped[int] = mapped_column(Integer, default=0)
    needs_json: Mapped[str] = mapped_column(Text, default="[]")
    priority_score: Mapped[float] = mapped_column(Float, default=0)
    priority_breakdown_json: Mapped[str] = mapped_column(Text, default="{}")
    response_coverage: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[Source] = relationship(back_populates="incidents")
    assignments: Mapped[list[Assignment]] = relationship(back_populates="incident")
    reports: Mapped[list[CitizenReport]] = relationship(back_populates="incident")


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    reporter_name: Mapped[str] = mapped_column(String(120), default="Anonymous")
    contact: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str] = mapped_column(Text, default="")
    cloudinary_public_id: Mapped[str] = mapped_column(String(255), default="")
    cloudinary_asset_id: Mapped[str] = mapped_column(String(255), default="")
    cloudinary_format: Mapped[str] = mapped_column(String(20), default="")
    image_storage_status: Mapped[str] = mapped_column(String(30), default="local")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    moderation_status: Mapped[str] = mapped_column(String(30), default="pending")
    ai_caption: Mapped[str] = mapped_column(Text, default="")
    ai_decision: Mapped[str] = mapped_column(String(30), default="needs_volunteer_review")
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    ai_model: Mapped[str] = mapped_column(String(180), default="")
    ai_provider: Mapped[str] = mapped_column(String(80), default="")
    ai_prompt_version: Mapped[str] = mapped_column(String(80), default="")
    ai_analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewed_by: Mapped[str] = mapped_column(String(120), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="reports")


class Volunteer(Base):
    __tablename__ = "volunteers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(140))
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(180), default="")
    home_location: Mapped[str] = mapped_column(String(180))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    services_json: Mapped[str] = mapped_column(Text, default="[]")
    skills_json: Mapped[str] = mapped_column(Text, default="[]")
    languages_json: Mapped[str] = mapped_column(Text, default="[]")
    preferred_places_json: Mapped[str] = mapped_column(Text, default="[]")
    availability: Mapped[str] = mapped_column(String(40), default="available")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_missions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assignments: Mapped[list[Assignment]] = relationship(back_populates="volunteer")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("incident_id", "volunteer_id", name="uq_assignment_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"), index=True)
    service: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="assigned", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    assigned_by: Mapped[str] = mapped_column(String(120), default="Demo administrator")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="assignments")
    volunteer: Mapped[Volunteer] = relationship(back_populates="assignments")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[Source] = relationship(back_populates="runs")
