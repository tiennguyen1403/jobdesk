from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class UpworkToken(Base):
    """Stored Upwork OAuth2 credentials — one row per provider (single-user).

    JobDesk is single-user and local-first, so there is exactly one logical token
    record per provider (``provider`` is unique). The row is created when the OAuth
    flow *starts* — holding only the pending CSRF ``auth_state`` — and filled with
    the access / refresh tokens once ``GET /api/upwork/callback`` exchanges the
    authorization code. So ``access_token`` is nullable and **"connected" means
    ``access_token IS NOT NULL``**, not merely that a row exists.

    These are secrets: they live only in the local DB, are never logged, and are
    sent nowhere but Upwork's token endpoint. The status endpoint and every schema
    deliberately expose only *whether* a token exists and its expiry — never the
    token values themselves.
    """

    __tablename__ = "upwork_token"

    id: Mapped[int] = mapped_column(primary_key=True)

    # One record per provider (single-user). 'upwork' today; kept generic so a
    # second OAuth source can reuse the table without a migration.
    provider: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, default="upwork"
    )

    # NULL until the callback completes: a row may exist mid-flow holding only the
    # pending auth_state. Tokens are secrets → Text, never indexed, never logged.
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scope: Mapped[str | None] = mapped_column(String, nullable=True)

    # Pending OAuth2 CSRF state: set when /connect starts the flow, checked and
    # cleared by /callback. NULL when no authorization is in flight.
    auth_state: Mapped[str | None] = mapped_column(String, nullable=True)

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
        state = "connected" if self.access_token else "disconnected"
        return f"<UpworkToken provider={self.provider!r} {state}>"
