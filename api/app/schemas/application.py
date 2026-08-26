from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.application import ApplicationStatus
from .job import ApplicationRead


class JobSummary(BaseModel):
    """Compact job facts for a pipeline card — enough to render the board without
    loading the full posting. Keeps the part-time signal (``workload`` /
    ``weekly_hours`` / ``duration``) visible so scope stays in view at a glance.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    url: str
    budget_type: str
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str
    workload: str | None = None
    weekly_hours: int | None = None
    duration: str | None = None


class ApplicationCard(ApplicationRead):
    """A board card: the pipeline application plus a summary of the job it tracks.

    Extends :class:`ApplicationRead` (the bare card embedded inside a job) with a
    ``job`` summary, since the board is application-first and needs the posting's
    headline facts alongside each card.
    """

    job: JobSummary


class ApplicationUpdate(BaseModel):
    """Partial update for a card (PATCH) — only keys present in the body change.

    ``status`` is validated against the pipeline enum. ``job_id`` and the
    timestamps are intentionally not updatable: a card never changes which job it
    tracks, and bookkeeping is managed by the ORM.
    """

    status: ApplicationStatus | None = None
    notes: str | None = None
    applied_at: datetime | None = None
