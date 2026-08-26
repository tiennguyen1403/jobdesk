from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SavedSearch(Base):
    """A reusable search definition the poller (#6) iterates.

    JobDesk polls providers on a schedule (the Upwork API has no webhooks), so
    the searches to run must be persisted rather than retyped each cycle. Each
    row is one named query for one provider; ``enabled`` toggles it in and out of
    the poll loop without deleting it, and ``last_polled_at`` records when it was
    last run (NULL = never polled).

    Part-time scope is first-class: the ``query`` JSONB carries not only
    keywords/category but the workload / max-weekly-hours constraints, so polling
    only pulls evenings-and-weekends-viable work — never full-time gigs. The
    query lives in JSONB rather than columns because its shape is
    provider-specific and grows as providers are added; the typed ``SearchQuery``
    schema keeps the part-time fields explicit and validated at the API boundary.
    A saved search only *finds* work — JobDesk never auto-applies.
    """

    __tablename__ = "saved_search"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Human label for the search (e.g. "Evening Python gigs").
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Provider key this search runs against: 'upwork' today, kept generic so a
    # second source can reuse the table without a migration.
    provider: Mapped[str] = mapped_column(String, nullable=False, default="upwork")

    # Keywords/category + first-class part-time constraints (workload,
    # max_weekly_hours). JSONB because the shape is provider-specific; the typed
    # SearchQuery schema validates the part-time fields at the API boundary.
    query: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Toggles this search in/out of the poll loop without deleting it.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # When the poller (#6) last ran this search. NULL = never polled.
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        state = "enabled" if self.enabled else "disabled"
        return f"<SavedSearch id={self.id} name={self.name!r} {state}>"
