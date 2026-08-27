from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class JobsAnalytics(BaseModel):
    """Jobs the tracker holds, broken down by the provider that supplied them.

    ``by_source`` always carries the four canonical sources (``manual`` /
    ``capture`` / ``upwork`` / ``freelancer``) — zero when none exist — so the
    Dashboard renders a stable shape; any other source seen in the data is added
    on top.
    """

    total: int
    by_source: dict[str, int]


class MatchBands(BaseModel):
    """Scored jobs bucketed by AI match score (0–100), inclusive bounds."""

    low: int  # 0–39
    medium: int  # 40–69
    high: int  # 70–100


class MatchAnalytics(BaseModel):
    """AI match-scoring coverage and distribution across all jobs.

    ``scored`` + ``unscored`` == jobs total (a NULL ``match_score`` means "not
    scored yet", never a scored 0). ``part_time_fit`` counts jobs the scorer
    explicitly flagged as fitting the evenings-and-weekends scope.
    """

    scored: int
    unscored: int
    part_time_fit: int
    bands: MatchBands


class PipelineAnalytics(BaseModel):
    """The application funnel as current counts per pipeline stage.

    There is no transition history, so this is a snapshot — counts by status,
    plus ``applied_conversion``: the fraction of cards that moved past ``saved``
    (i.e. you applied on the platform), 0.0 when the pipeline is empty.
    """

    total: int
    by_status: dict[str, int]
    applied_conversion: float


class AiFeatureCost(BaseModel):
    """AI spend and usage rolled up for one feature (e.g. ``score_match``)."""

    feature: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    runs: int


class AiDailySpend(BaseModel):
    """AI spend and usage for a single UTC calendar day within the window."""

    date: date
    cost_usd: float
    input_tokens: int
    output_tokens: int
    runs: int


class AiAnalytics(BaseModel):
    """Claude usage ledger: lifetime totals, a per-feature split, and a recent
    daily series over the trailing ``days`` window (sparse — only days with runs).
    """

    total_cost_usd: float
    input_tokens: int
    output_tokens: int
    by_feature: list[AiFeatureCost]
    days: int
    recent: list[AiDailySpend]


class AnalyticsSummary(BaseModel):
    """Everything the Dashboard needs in one payload — aggregated from JobDesk's
    own tables (``job`` / ``application`` / ``ai_run``); no new tables involved.
    """

    jobs: JobsAnalytics
    match: MatchAnalytics
    pipeline: PipelineAnalytics
    ai: AiAnalytics
