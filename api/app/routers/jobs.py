from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..ai import score_match
from ..db import get_db
from ..models import Application, ApplicationStatus, Job
from ..providers import ManualProvider
from ..schemas.ai import ScoreMatchResponse
from ..schemas.application import ApplicationCard
from ..schemas.job import JobCreate, JobRead, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])

# The manual provider is stateless, so a single shared instance is enough.
_provider = ManualProvider()


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> Job:
    """Normalize a hand-entered job, persist it, and open its pipeline card.

    The input is routed through :class:`ManualProvider` so a manual posting is
    normalized exactly like one from any other source. Every new job enters the
    tracker at stage ``saved`` — JobDesk never auto-applies; applying stays a
    manual step on the platform.
    """
    # ``mode="json"`` makes the payload JSON-native (e.g. datetimes -> ISO
    # strings) so the copy kept in the JSONB ``raw`` column is serializable.
    normalized = _provider.fetch(payload.model_dump(mode="json"))
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No job to create."
        )

    job = Job(source=_provider.key, **normalized[0].model_dump())
    job.application = Application(status=ApplicationStatus.saved)

    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(
    db: Session = Depends(get_db),
    workload: Literal["part_time", "full_time"] | None = Query(
        default=None, description="Keep only jobs with this workload (scope guardrail)."
    ),
    max_weekly_hours: int | None = Query(
        default=None, ge=0, description="Keep only jobs whose weekly_hours is <= this."
    ),
    budget_type: Literal["hourly", "fixed"] | None = Query(
        default=None, description="Keep only hourly or fixed-price jobs."
    ),
    q: str | None = Query(default=None, description="Free-text match on title / description."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Job]:
    """List jobs, newest first, narrowed by the part-time scope filters."""
    stmt = select(Job).options(selectinload(Job.application))

    if workload is not None:
        stmt = stmt.where(Job.workload == workload)
    if max_weekly_hours is not None:
        # Jobs with an unknown (NULL) weekly_hours are excluded: an unstated
        # workload can't be confirmed to fit the available evenings/weekends.
        stmt = stmt.where(Job.weekly_hours <= max_weekly_hours)
    if budget_type is not None:
        stmt = stmt.where(Job.budget_type == budget_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Job.title.ilike(like) | Job.description.ilike(like))

    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)) -> Job:
    """Patch a job's fields. Only keys present in the body are changed."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)

    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/score-match", response_model=ScoreMatchResponse)
def score_job_match(job_id: int, db: Session = Depends(get_db)) -> ScoreMatchResponse:
    """Score how well a job fits as a part-time / evenings-and-weekends side gig.

    Runs the AI ``score_match`` feature (Claude, structured output), then persists
    the score / reasons / part-time flag on the job and logs the call to ``ai_run``.
    Scoring weighs availability (workload / weekly hours / duration) above skill
    match, so a full_time-leaning posting lands low. A missing API key returns 503
    and an upstream failure 502 (both handled centrally); on either error the job
    is left unscored because ``score_match`` raises before any column is written.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    match = score_match(db, job)

    job.match_score = match.score
    job.match_reasons = match.reasons
    job.match_part_time_fit = match.part_time_fit
    job.match_scored_at = datetime.now(timezone.utc)
    db.commit()

    return ScoreMatchResponse(
        job_id=job_id,
        score=match.score,
        reasons=match.reasons,
        part_time_fit=match.part_time_fit,
        model=match.result.model,
        cost_usd=match.result.cost_usd,
        run_id=match.result.run.id,
    )


@router.post(
    "/{job_id}/application",
    response_model=ApplicationCard,
    status_code=status.HTTP_201_CREATED,
)
def create_application(job_id: int, db: Session = Depends(get_db)) -> Application:
    """Open a pipeline card for an existing job that has none yet.

    Jobs added via ``POST /api/jobs`` already start with a card, so this covers
    postings inserted by other providers (capture, Upwork) that arrive without
    one. The card enters at ``saved`` — JobDesk never auto-applies.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.application is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Job already has an application."
        )

    job.application = Application(status=ApplicationStatus.saved)
    db.add(job)
    db.commit()
    db.refresh(job.application)
    return job.application


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a job and its pipeline card (1–1 cascade)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
