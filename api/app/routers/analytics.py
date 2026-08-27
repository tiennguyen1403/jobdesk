"""Dashboard analytics — aggregates JobDesk's own data, no new tables.

A single read-only endpoint that rolls up the ``job``, ``application`` and
``ai_run`` tables into the numbers the Dashboard renders. Aggregation happens in
SQL (GROUP BY + FILTER) wherever it's reasonable; the router only assembles the
typed payload. Everything returns zeros on an empty database.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AiRun, Application, ApplicationStatus, Job
from ..schemas.analytics import (
    AiAnalytics,
    AiDailySpend,
    AiFeatureCost,
    AnalyticsSummary,
    JobsAnalytics,
    MatchAnalytics,
    MatchBands,
    PipelineAnalytics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# The canonical job sources, always present in ``jobs.by_source`` so the
# Dashboard has a stable shape even before a provider has ingested anything.
CANONICAL_SOURCES = ("manual", "capture", "upwork", "freelancer")


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    db: Session = Depends(get_db),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Trailing window (in days) for the AI daily-spend series.",
    ),
) -> AnalyticsSummary:
    """Aggregate jobs, the application funnel and AI cost for the Dashboard."""
    # --- Jobs: total + count by source -------------------------------------
    by_source: dict[str, int] = {src: 0 for src in CANONICAL_SOURCES}
    for source, count in db.execute(
        select(Job.source, func.count()).group_by(Job.source)
    ):
        by_source[source] = count
    jobs = JobsAnalytics(total=sum(by_source.values()), by_source=by_source)

    # --- Match scoring: coverage + banded distribution (one pass) ----------
    scored, unscored, low, medium, high, part_time_fit = db.execute(
        select(
            func.count().filter(Job.match_score.isnot(None)),
            func.count().filter(Job.match_score.is_(None)),
            func.count().filter(Job.match_score.between(0, 39)),
            func.count().filter(Job.match_score.between(40, 69)),
            func.count().filter(Job.match_score.between(70, 100)),
            func.count().filter(Job.match_part_time_fit.is_(True)),
        )
    ).one()
    match = MatchAnalytics(
        scored=scored,
        unscored=unscored,
        part_time_fit=part_time_fit,
        bands=MatchBands(low=low, medium=medium, high=high),
    )

    # --- Pipeline: current counts by status + applied conversion -----------
    by_status: dict[str, int] = {member.value: 0 for member in ApplicationStatus}
    for st, count in db.execute(
        select(Application.status, func.count()).group_by(Application.status)
    ):
        key = st.value if isinstance(st, ApplicationStatus) else str(st)
        by_status[key] = count
    pipeline_total = sum(by_status.values())
    # "Applied" = any card past the first column; no transition history exists,
    # so this is the closest honest conversion signal we can derive.
    applied = pipeline_total - by_status[ApplicationStatus.saved.value]
    pipeline = PipelineAnalytics(
        total=pipeline_total,
        by_status=by_status,
        applied_conversion=round(applied / pipeline_total, 4) if pipeline_total else 0.0,
    )

    # --- AI cost: lifetime totals, by feature, and a recent daily series ---
    total_cost, total_in, total_out = db.execute(
        select(
            func.coalesce(func.sum(AiRun.cost_usd), 0.0),
            func.coalesce(func.sum(AiRun.input_tokens), 0),
            func.coalesce(func.sum(AiRun.output_tokens), 0),
        )
    ).one()

    by_feature = [
        AiFeatureCost(
            feature=feature,
            cost_usd=round(cost, 6),
            input_tokens=in_tok,
            output_tokens=out_tok,
            runs=runs,
        )
        for feature, cost, in_tok, out_tok, runs in db.execute(
            select(
                AiRun.feature,
                func.coalesce(func.sum(AiRun.cost_usd), 0.0),
                func.coalesce(func.sum(AiRun.input_tokens), 0),
                func.coalesce(func.sum(AiRun.output_tokens), 0),
                func.count(),
            )
            .group_by(AiRun.feature)
            .order_by(func.sum(AiRun.cost_usd).desc(), AiRun.feature)
        )
    ]

    # Bucket by UTC calendar day, independent of the DB session's time zone.
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    day = cast(func.timezone("UTC", AiRun.created_at), Date)
    recent = [
        AiDailySpend(
            date=spend_date,
            cost_usd=round(cost, 6),
            input_tokens=in_tok,
            output_tokens=out_tok,
            runs=runs,
        )
        for spend_date, cost, in_tok, out_tok, runs in db.execute(
            select(
                day.label("day"),
                func.coalesce(func.sum(AiRun.cost_usd), 0.0),
                func.coalesce(func.sum(AiRun.input_tokens), 0),
                func.coalesce(func.sum(AiRun.output_tokens), 0),
                func.count(),
            )
            .where(AiRun.created_at >= threshold)
            .group_by(day)
            .order_by(day)
        )
    ]

    ai = AiAnalytics(
        total_cost_usd=round(total_cost, 6),
        input_tokens=total_in,
        output_tokens=total_out,
        by_feature=by_feature,
        days=days,
        recent=recent,
    )

    return AnalyticsSummary(jobs=jobs, match=match, pipeline=pipeline, ai=ai)
