from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.application import ApplicationStatus

# Kept in sync with NormalizedJob (app.providers.base): the API speaks the same
# vocabulary the provider layer normalizes to.
BudgetType = Literal["hourly", "fixed"]
Workload = Literal["part_time", "full_time"]


class JobBase(BaseModel):
    """The writable fields of a job, mirroring the NormalizedJob shape."""

    url: str
    title: str
    description: str = ""
    external_id: str | None = None

    budget_type: BudgetType = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "USD"

    # --- Side-gig scope: part-time / hourly / project work only ---
    workload: Workload | None = None
    weekly_hours: int | None = Field(default=None, ge=0)
    duration: str | None = None

    skills: list[str] = Field(default_factory=list)
    client_country: str | None = None
    posted_at: datetime | None = None


class JobCreate(JobBase):
    """Payload to add a job by hand (POST /api/jobs). Source is always 'manual'."""


class JobUpdate(BaseModel):
    """Partial update (PATCH /api/jobs/{id}) — every field is optional.

    ``source`` and the timestamps are intentionally not updatable: a posting's
    origin never changes, and bookkeeping is managed by the ORM.
    """

    url: str | None = None
    title: str | None = None
    description: str | None = None
    external_id: str | None = None

    budget_type: BudgetType | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str | None = None

    workload: Workload | None = None
    weekly_hours: int | None = Field(default=None, ge=0)
    duration: str | None = None

    skills: list[str] | None = None
    client_country: str | None = None
    posted_at: datetime | None = None


class ApplicationRead(BaseModel):
    """The 1–1 pipeline card returned alongside a job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ApplicationStatus
    notes: str | None = None
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobRead(BaseModel):
    """A persisted job as returned by the API, with its pipeline card."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str | None = None
    url: str
    title: str
    description: str
    budget_type: str
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str
    workload: str | None = None
    weekly_hours: int | None = None
    duration: str | None = None
    skills: list[str]
    client_country: str | None = None
    posted_at: datetime | None = None
    # --- AI match scoring (score_match); null until the job is scored ---
    match_score: int | None = None
    match_reasons: list[str] | None = None
    match_part_time_fit: bool | None = None
    match_scored_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    application: ApplicationRead | None = None
