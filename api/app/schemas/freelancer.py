from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FreelancerStatus(BaseModel):
    """Freelancer connection status — deliberately free of any token value.

    Returned by ``GET /api/freelancer/status`` (and by ``callback`` /
    ``disconnect``), it reports only *whether* an account is connected and when the
    access token expires — never the access/refresh tokens themselves, which are
    secrets.
    """

    provider: str = "freelancer"
    connected: bool
    expired: bool
    expires_at: datetime | None = None
    scope: str | None = None
