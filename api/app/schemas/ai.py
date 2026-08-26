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
