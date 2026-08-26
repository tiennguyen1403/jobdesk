from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .job import JobRead


class CapturePayload(BaseModel):
    """A browser-scraped job posting sent to ``POST /api/capture``.

    Only ``url`` and ``title`` are required — a scrape reliably yields those
    (``document.title`` is the last-resort title). Every other field is a
    best-effort hint that :class:`~app.providers.capture.CaptureProvider`
    normalizes or drops. ``extra='allow'`` keeps any additional scraped keys the
    bookmarklet sends (e.g. ``captured_at``); they are preserved verbatim in the
    job's ``raw`` column for later re-parsing.
    """

    model_config = ConfigDict(extra="allow")

    url: str
    title: str
    description: str = ""
    external_id: str | None = None

    budget_type: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str | None = None

    workload: str | None = None
    weekly_hours: int | None = Field(default=None, ge=0)
    duration: str | None = None

    skills: list[str] = Field(default_factory=list)
    client_country: str | None = None
    posted_at: datetime | None = None


class CaptureResult(BaseModel):
    """The ingest summary returned by ``POST /api/capture``.

    ``created`` / ``updated`` / ``skipped`` mirror the shared ingestion service,
    so re-capturing the same posting shows ``created=0, updated=1`` (deduped, no
    new row). ``jobs`` carries the affected job(s) so the bookmarklet can confirm
    the title it saved.
    """

    source: str
    created: int
    updated: int
    skipped: int
    job_ids: list[int]
    jobs: list[JobRead] = Field(default_factory=list)
