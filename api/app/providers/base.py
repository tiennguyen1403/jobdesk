from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class NormalizedJob(BaseModel):
    """Normalized job shape that every provider returns.

    Because of this, the rest of the app (pipeline / CV / AI / UI) never depends
    on where a job came from (Manual, Browser Capture, Upwork API, Freelancer.com, ...).
    """

    external_id: str | None = None      # id on the source platform (None for manual entry)
    url: str
    title: str
    description: str = ""

    budget_type: str = "fixed"          # 'hourly' | 'fixed'
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "USD"

    # --- Side-gig scope: only part-time / hourly / project work ---
    workload: str | None = None         # 'part_time' | 'full_time'
    weekly_hours: int | None = None     # estimated hours/week (to filter for evenings & weekends)
    duration: str | None = None         # e.g. 'less_than_1_month' | 'one_to_three_months' | 'ongoing'

    skills: list[str] = []
    client_country: str | None = None
    posted_at: datetime | None = None

    raw: dict = {}                      # original payload (audit / re-parse later)


class JobProvider(ABC):
    """Pluggable interface for every job source."""

    key: str = "base"                   # 'manual' | 'capture' | 'upwork' | ...
    supports_polling: bool = False      # True if it can be polled on a schedule (APScheduler)

    @abstractmethod
    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        """Return a list of normalized jobs."""
        ...
