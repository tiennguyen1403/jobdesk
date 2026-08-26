from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Cv(Base):
    """A stored CV in markdown — a base/master CV or a per-job tailored variant.

    ``job_id`` is NULL for a base CV (reusable, not tied to any posting) and set
    when the CV was tailored for a specific job. This model is pure storage:
    generating tailored content with Claude is a separate Phase 2 step
    (``tailor_cv``). Deleting a job cascades away its tailored CVs; base CVs,
    having no ``job_id``, are untouched.
    """

    __tablename__ = "cv"

    id: Mapped[int] = mapped_column(primary_key=True)

    label: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # NULL = base/master CV; set = tailored for that job. CASCADE: a tailored CV
    # is meaningless without its job, so it dies with it (base CVs are NULL here).
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=True, index=True
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
        return f"<Cv id={self.id} label={self.label!r} job_id={self.job_id}>"
