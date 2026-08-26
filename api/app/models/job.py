from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .application import Application


class Job(Base):
    """A normalized job posting persisted from any provider.

    Faithful superset of ``NormalizedJob`` (see ``app.providers.base``) so any
    provider — manual, capture, Upwork, ... — can persist a posting without
    loss. Part-time / hourly / project scope only.
    """

    __tablename__ = "job"
    __table_args__ = (
        # A posting is unique per source; manual entries have external_id=NULL,
        # which Postgres treats as distinct, so multiple manual jobs are allowed.
        UniqueConstraint("source", "external_id", name="uq_job_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Provider key this posting came from: 'manual' | 'capture' | 'upwork' | ...
    source: Mapped[str] = mapped_column(String, nullable=False)

    # --- NormalizedJob fields (kept a faithful superset) ---
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    budget_type: Mapped[str] = mapped_column(String, nullable=False, default="fixed")  # 'hourly' | 'fixed'
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")

    # --- Side-gig scope: part-time / hourly / project work only ---
    workload: Mapped[str | None] = mapped_column(String, nullable=True)  # 'part_time' | 'full_time'
    weekly_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[str | None] = mapped_column(String, nullable=True)

    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    client_country: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Bookkeeping ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 1–1 pipeline card (created when the job enters the tracker).
    application: Mapped[Application | None] = relationship(
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Job id={self.id} source={self.source!r} title={self.title!r}>"
