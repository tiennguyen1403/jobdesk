from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AiRunRead(BaseModel):
    """One row of the AI cost/usage ledger, as returned by GET /api/ai/runs."""

    # protected_namespaces=() lets us keep the natural field name ``model``.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    feature: str
    model: str
    status: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None
    job_id: int | None = None
    created_at: datetime


class ScoreMatchResponse(BaseModel):
    """The score_match result for a job, plus the accounting logged for the call."""

    model_config = ConfigDict(protected_namespaces=())

    job_id: int
    score: int  # 0–100, higher = better evenings-and-weekends fit
    reasons: list[str]
    part_time_fit: bool
    model: str
    cost_usd: float
    run_id: int


class TailorCvRequest(BaseModel):
    """Optional body for POST /api/jobs/{id}/tailor-cv.

    ``base_cv_id`` chooses which base/master CV to tailor from; omit it (or send an
    empty body) to use the most recently created base CV.
    """

    base_cv_id: int | None = None


class TailorCvResponse(BaseModel):
    """The tailor_cv result: the saved tailored CV plus the call's accounting."""

    model_config = ConfigDict(protected_namespaces=())

    job_id: int
    cv_id: int  # the new tailored cv row
    base_cv_id: int  # the base CV it was tailored from
    label: str
    content: str  # the tailored CV, as structured markdown
    model: str
    cost_usd: float
    run_id: int


class DraftProposalRequest(BaseModel):
    """Optional body for POST /api/jobs/{id}/draft-proposal.

    ``cv_id`` picks a CV to ground the proposal in (the freelancer's real
    background — a base CV or one already tailored for this job). Omit it (or send
    an empty body) to auto-pick: the CV already tailored for this job if one
    exists, else the newest base CV, else draft without a CV.
    """

    cv_id: int | None = None


class DraftProposalResponse(BaseModel):
    """The draft_proposal result: the saved proposal plus the call's accounting."""

    model_config = ConfigDict(protected_namespaces=())

    job_id: int
    proposal_id: int  # the new proposal row
    cv_id: int | None  # the CV it was grounded in, if any (None if drafted without one)
    content: str  # the proposal draft, as markdown
    model: str
    cost_usd: float
    run_id: int


class SmokeRequest(BaseModel):
    """Optional body for the smoke call; defaults to a trivial ping prompt."""

    prompt: str | None = None


class SmokeResponse(BaseModel):
    """The smoke call's answer plus the accounting logged for it."""

    model_config = ConfigDict(protected_namespaces=())

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    run_id: int
