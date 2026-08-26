from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Proposal(Base):
    """A proposal draft written for one job, editable before applying.

    Unlike a :class:`Cv` — which can be a reusable base CV with a NULL
    ``job_id`` — a proposal is always about a specific posting (it argues fit
    for *that* job), so ``job_id`` is required. A job may hold several drafts
    (1–many), so this is not a unique FK. Pure storage: producing the text with
    Claude is a separate Phase 2 step (``draft_proposal``); JobDesk never
    auto-submits — the draft is applied manually on the platform. Deleting a job
    cascades away its proposals.
    """

    __tablename__ = "proposal"

    id: Mapped[int] = mapped_column(primary_key=True)

    # A proposal is meaningless without its job, so it dies with it (CASCADE).
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

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
        return f"<Proposal id={self.id} job_id={self.job_id}>"
