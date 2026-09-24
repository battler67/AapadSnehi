from datetime import datetime, timezone, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=2000, allow_inf_nan=False)


class Address(Strict):
    state: str = Field("", max_length=120)
    city: str = Field("", max_length=120)
    locality: str = Field("", max_length=120)
    ward: str = Field("", max_length=80)
    street: str = Field("", max_length=160)
    street_number: str = Field("", max_length=50)
    building: str = Field("", max_length=160)
    door: str = Field("", max_length=60)
    floor: str = Field("", max_length=40)
    landmark: str = Field("", max_length=200)
    directions: str = Field("", max_length=1000)


class Location(Strict):
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    source: Literal["device_gps", "photo_metadata", "address_lookup", "manual_pin", "text"] = "text"
    accuracy: float | None = Field(None, ge=0, le=100000)
    confirmed: bool = False
    precision: Literal["building", "street", "locality", "unknown"] = "unknown"

    @model_validator(mode="after")
    def coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both coordinates or neither")
        if self.confirmed and self.latitude is None:
            raise ValueError("A pin must exist before it can be confirmed")
        if self.precision == "building" and (not self.confirmed or (self.accuracy or 0) > 50):
            raise ValueError("Building precision requires a confirmed pin with accuracy within 50 metres")
        return self


class Submission(Strict):
    idempotency_key: str = Field(min_length=16, max_length=80)
    reporter_token: str = Field(min_length=32, max_length=128)
    kind: Literal["flood", "rescue", "blocked", "update"]
    update_incident_id: int | None = Field(None, ge=1)
    location: Location = Field(default_factory=Location)
    address: Address = Field(default_factory=Address)
    observed_at: datetime | None = None
    time_quality: Literal["exact", "approximate", "unknown"] = "unknown"
    water_level: Literal["ankle", "knee", "waist", "above_waist", "unknown"] = "unknown"
    trend: Literal["rising", "stable", "receding", "unknown"] = "unknown"
    access: Literal["passable_reported", "blocked", "unknown"] = "unknown"
    description: str = ""
    people: int | None = Field(None, ge=0, le=100000)
    count_quality: Literal["exact", "estimated", "unknown"] = "unknown"
    position: str = Field("", max_length=300)
    assistance: list[Literal["limited_mobility", "urgent_medical", "children", "transport", "other"]] = Field(default_factory=list, max_length=5)
    contact: str = Field("", max_length=40)
    reporter_present: bool = True

    @model_validator(mode="after")
    def usable(self):
        if not self.location.confirmed and len(" ".join([self.address.locality, self.address.street, self.address.landmark, self.address.directions]).strip()) < 5:
            raise ValueError("Confirm a pin or provide a usable locality, street, landmark or directions")
        if self.time_quality == "unknown":
            self.observed_at = None
        elif not self.observed_at or self.observed_at.tzinfo is None:
            raise ValueError("Observed time needs a timezone, or select unknown")
        elif self.observed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Observation cannot be in the future")
        if self.count_quality == "unknown":
            self.people = None
        elif self.people is None:
            raise ValueError("Enter the reported count or select unknown")
        if self.kind == "update" and self.update_incident_id is None:
            raise ValueError("An update needs an incident reference")
        return self


class Review(Strict):
    version: int
    report_id: int
    verification: Literal["unverified", "corroborated", "responder_verified", "disputed"]
    urgency: Literal["review", "routine", "high", "critical"]
    reason: str = Field(min_length=5)
    confirmed_people: int | None = Field(None, ge=0, le=100000)
    status: Literal["active", "monitoring", "closed"] = "active"


class Transition(Strict):
    version: int
    state: Literal["needs_review", "ready", "assigned", "en_route", "on_scene", "resolved", "unable_to_reach", "cancelled"]
    team_id: str | None = None
    note: str = Field(min_length=3)
    outcome: str = ""
    assisted: int | None = Field(None, ge=0, le=100000)
    remaining: str = ""


class Relocate(Strict):
    version: int
    location: Location
    reason: str = Field(min_length=5)


class Regroup(Strict):
    version: int
    target_incident_id: int | None = None
    reason: str = Field(min_length=5)


class Merge(Strict):
    version: int
    target_incident_id: int
    target_version: int
    reason: str = Field(min_length=5)
    acknowledge_tasks: bool = False
