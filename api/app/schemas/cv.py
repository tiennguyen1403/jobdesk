from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CvBase(BaseModel):
    """The writable fields of a CV."""

    label: str
    content: str = ""
    # NULL = base/master CV; set = tailored for that job.
    job_id: int | None = None


class CvCreate(CvBase):
    """Payload to create a CV (POST /api/cvs)."""


class CvUpdate(BaseModel):
    """Partial update (PATCH /api/cvs/{id}) — only keys present in the body change.

    Sending ``job_id: null`` re-files a tailored CV as a base CV; omitting the key
    leaves it as is. The timestamps are managed by the ORM and are not updatable.
    """

    label: str | None = None
    content: str | None = None
    job_id: int | None = None


class CvRead(BaseModel):
    """A persisted CV as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    content: str
    job_id: int | None = None
    created_at: datetime
    updated_at: datetime
