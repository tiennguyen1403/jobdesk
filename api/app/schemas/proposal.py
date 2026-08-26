from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProposalBase(BaseModel):
    """The writable fields of a proposal."""

    # Required: a proposal always belongs to a specific job (no base proposal).
    job_id: int
    content: str = ""


class ProposalCreate(ProposalBase):
    """Payload to create a proposal (POST /api/proposals)."""


class ProposalUpdate(BaseModel):
    """Partial update (PATCH /api/proposals/{id}) — only keys present change.

    Editing ``content`` bumps ``updated_at`` (managed by the ORM). A proposal is
    written for its job and is not re-filed elsewhere, so ``job_id`` is not
    updatable — draft a new one for a different job instead.
    """

    content: str | None = None


class ProposalRead(BaseModel):
    """A persisted proposal as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    content: str
    created_at: datetime
    updated_at: datetime
