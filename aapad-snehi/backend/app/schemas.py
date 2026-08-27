from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class IncidentCandidate(BaseModel):
    external_id: str
    title: str = Field(min_length=3, max_length=240)
    description: str = ""
    disaster_type: str
    severity: int = Field(ge=1, le=5)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    location_name: str = ""
    occurred_at: datetime
    source_kind: str
    verification_status: str
    source_url: str = ""
    affected_estimate: int = Field(default=0, ge=0)
    needs: list[str] = Field(default_factory=list)


class VolunteerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    phone: str = Field(min_length=7, max_length=30)
    email: str = Field(default="", max_length=180)
    home_location: str = Field(min_length=2, max_length=180)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    services: list[str] = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    preferred_places: list[str] = Field(min_length=1, max_length=5)
    availability: str = "available"

    @field_validator("services", "skills", "languages")
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @field_validator("preferred_places")
    @classmethod
    def normalize_preferred_places(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            place = " ".join(value.split())
            if not 2 <= len(place) <= 120:
                raise ValueError("Each preferred place must contain 2 to 120 characters")
            identity = place.casefold()
            if identity not in seen:
                seen.add(identity)
                normalized.append(place)
        if not normalized:
            raise ValueError("At least one preferred place is required")
        return normalized


class AssignmentCreate(BaseModel):
    incident_id: int
    volunteer_id: int
    service: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=600)


class DistributionRequest(BaseModel):
    incident_ids: list[int] = Field(min_length=1, max_length=10)
    volunteer_ids: list[int] = Field(min_length=1, max_length=50)
    strategy: str = Field(default="balanced-greedy-v1", min_length=2, max_length=80)
    commit: bool = False
    preview_token: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=600)

    @field_validator("incident_ids", "volunteer_ids")
    @classmethod
    def unique_ids(cls, values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))


class ClaimCreate(BaseModel):
    volunteer_id: int
    service: str = Field(min_length=2, max_length=80)


class GovernmentSourceCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    authority: str = Field(min_length=3, max_length=180)
    endpoint: HttpUrl
    enabled: bool = True


class IngestionRequest(BaseModel):
    source_ids: list[int] = Field(default_factory=list)
    live: bool = False


class ReportModerationUpdate(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer_name: str = Field(default="Volunteer reviewer", min_length=2, max_length=120)


class BlueskyScanRequest(BaseModel):
    query: str = Field(default="", max_length=100)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
