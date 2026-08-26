from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Reuse the job vocabulary (app.schemas.job): JobDesk is part-time only, so a
# search constrains to the same workload values a job carries.
Workload = Literal["part_time", "full_time"]


class SearchQuery(BaseModel):
    """The typed shape of a saved search's ``query`` JSONB.

    Keywords/category say *what* to search for; the part-time constraints
    (``workload`` / ``max_weekly_hours``) are first-class so the poller (#6) only
    pulls evenings-and-weekends-viable work. Extra provider-specific keys are
    allowed to pass through so a new provider can extend the query without a
    migration, and so any such keys round-trip faithfully on read.
    """

    model_config = ConfigDict(extra="allow")

    # What to search for.
    keywords: str = ""
    category: str | None = None

    # --- Part-time constraints (first-class) ---
    # Desired workload; 'part_time' keeps the poll within side-gig scope.
    workload: Workload | None = None
    # Drop postings above this weekly-hours cap.
    max_weekly_hours: int | None = Field(default=None, ge=0)


class SavedSearchBase(BaseModel):
    """The writable fields of a saved search."""

    name: str
    provider: str = "upwork"
    query: SearchQuery = Field(default_factory=SearchQuery)
    enabled: bool = True


class SavedSearchCreate(SavedSearchBase):
    """Payload to create a saved search (POST /api/saved-searches)."""


class SavedSearchUpdate(BaseModel):
    """Partial update (PATCH /api/saved-searches/{id}) — only keys present change.

    ``query`` is replaced wholesale when supplied (not deep-merged). The poll
    bookkeeping (``last_polled_at``) and the timestamps are managed by the poller
    and the ORM, so they are intentionally not client-updatable here.
    """

    name: str | None = None
    provider: str | None = None
    query: SearchQuery | None = None
    enabled: bool | None = None


class SavedSearchRead(BaseModel):
    """A persisted saved search as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: str
    query: SearchQuery
    enabled: bool
    last_polled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
