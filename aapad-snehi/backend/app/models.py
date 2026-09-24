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
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
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


class EdgeDevice(Base):
    __tablename__ = "edge_devices"

    device_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    device_type: Mapped[str] = mapped_column(String(40), index=True)
    installed_purposes_json: Mapped[str] = mapped_column(Text, default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    region_id: Mapped[str] = mapped_column(String(80), index=True)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    simulation_only: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="registered", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    high_water_sequence: Mapped[int] = mapped_column(Integer, default=-1)
    battery_pct: Mapped[float] = mapped_column(Float, default=100)
    signal_quality_pct: Mapped[float] = mapped_column(Float, default=100)
    trust_score: Mapped[float] = mapped_column(Float, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    observations: Mapped[list[EdgeObservation]] = relationship(back_populates="device")


class EdgeSimulationRun(Base):
    __tablename__ = "edge_simulation_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(100), index=True)
    region_id: Mapped[str] = mapped_column(String(80), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    number_of_devices: Mapped[int] = mapped_column(Integer)
    speed_multiplier: Mapped[float] = mapped_column(Float)
    timestep_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="starting", index=True)
    cursor_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    emitted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EdgeObservation(Base):
    __tablename__ = "edge_observations"
    __table_args__ = (
        UniqueConstraint("device_id", "sequence_number", name="uq_edge_observation_device_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("edge_devices.device_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("edge_simulation_runs.run_id"), nullable=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(12))
    device_type: Mapped[str] = mapped_column(String(40), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    battery_pct: Mapped[float] = mapped_column(Float)
    signal_quality_pct: Mapped[float] = mapped_column(Float)
    source_protocol: Mapped[str] = mapped_column(String(20), default="http")
    quality_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    normalized_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    simulation_metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    device: Mapped[EdgeDevice] = relationship(back_populates="observations")
    measurements: Mapped[list[EdgeMeasurement]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class EdgeMeasurement(Base):
    __tablename__ = "edge_measurements"
    __table_args__ = (
        UniqueConstraint("observation_id", "property_name", name="uq_edge_measurement_property"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("edge_observations.id"), index=True)
    property_name: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30))

    observation: Mapped[EdgeObservation] = relationship(back_populates="measurements")


class EdgeFeatureSnapshot(Base):
    __tablename__ = "edge_feature_snapshots"
    __table_args__ = (
        UniqueConstraint("device_id", "hazard", "as_of", name="uq_edge_feature_device_hazard_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("edge_devices.device_id"), index=True)
    hazard: Mapped[str] = mapped_column(String(30), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pipeline_version: Mapped[str] = mapped_column(String(80))
    features_json: Mapped[str] = mapped_column(Text)
    observation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    data_quality: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EdgeRiskAssessment(Base):
    __tablename__ = "edge_risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("edge_devices.device_id"), index=True)
    feature_snapshot_id: Mapped[int] = mapped_column(ForeignKey("edge_feature_snapshots.id"), index=True)
    hazard: Mapped[str] = mapped_column(String(30), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    probability: Mapped[float] = mapped_column(Float)
    rule_score: Mapped[float] = mapped_column(Float)
    classifier_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(30), index=True)
    data_quality: Mapped[float] = mapped_column(Float)
    agreement_count: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(80))
    model_status: Mapped[str] = mapped_column(String(30), default="loaded")
    contributors_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EdgeRiskEvent(Base):
    __tablename__ = "edge_risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(180), index=True)
    hazard: Mapped[str] = mapped_column(String(30), index=True)
    region_id: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(30), default="WATCH", index=True)
    probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    data_quality: Mapped[float] = mapped_column(Float)
    contributing_device_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    latest_assessment_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="unreviewed")
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EdgeRiskTransition(Base):
    __tablename__ = "edge_risk_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("edge_risk_events.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EdgeRiskReview(Base):
    __tablename__ = "edge_risk_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("edge_risk_events.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    reviewer_name: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text, default="")
    confirm_demo_only: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
