from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AiRun(Base):
    """One audit row per Claude call — the AI layer's cost/usage ledger.

    Every call through :func:`app.ai.service.call_claude` writes exactly one row,
    on success *and* on failure, so token spend and errors are always accountable.
    This is the foundation the Phase 2 features (``score_match`` / ``tailor_cv`` /
    ``draft_proposal``) log against; ``feature`` names which one made the call.
    """

    __tablename__ = "ai_run"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Which AI feature made the call: 'smoke' | 'score_match' | 'tailor_cv' | ...
    feature: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # The model id actually used (echoed by the API on success; requested on failure).
    model: Mapped[str] = mapped_column(String, nullable=False)
    # Outcome of the call. Free-form string (not an enum) so new outcomes —
    # 'refusal', 'timeout', ... — can be recorded without a schema migration.
    status: Mapped[str] = mapped_column(String, nullable=False)  # 'success' | 'error'

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Short error summary when status='error'; NULL on success.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional link to the job this call was about (e.g. score_match). SET NULL on
    # delete: a cost record is an audit trail and must outlive the job it referenced.
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("job.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<AiRun id={self.id} feature={self.feature!r} "
            f"status={self.status!r} cost_usd={self.cost_usd}>"
        )
