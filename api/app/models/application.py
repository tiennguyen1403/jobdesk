from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .job import Job


class ApplicationStatus(str, enum.Enum):
    """Pipeline stage of an application (one Kanban column each)."""

    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"


class Application(Base):
    """Pipeline card: 1–1 with a :class:`Job`, tracking it through the funnel.

    JobDesk never auto-applies — applying is done manually on the platform; this
    row only records where the application stands and any notes about it.
    """

    __tablename__ = "application"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Unique FK enforces the 1–1 with Job; deleting a job removes its card.
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(
            ApplicationStatus,
            name="application_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ApplicationStatus.saved,
        server_default=text(f"'{ApplicationStatus.saved.value}'"),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    job: Mapped[Job] = relationship(back_populates="application")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Application id={self.id} job_id={self.job_id} status={self.status.value}>"
