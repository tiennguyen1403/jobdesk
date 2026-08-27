from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..ai import draft_proposal, score_match, tailor_cv
from ..db import get_db
from ..models import Application, ApplicationStatus, Cv, Job, Proposal
from ..providers import ManualProvider
from ..schemas.ai import (
    DraftProposalRequest,
    DraftProposalResponse,
    ScoreMatchResponse,
    TailorCvRequest,
    TailorCvResponse,
)
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No job to create."
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
    exclude_full_time: bool = Query(
        default=False,
        description=(
            "Part-time scope lens: keep jobs that are not full-time — part_time OR "
            "an unspecified (NULL) workload. Excludes only known full_time postings, "
            "so gig sources that report no workload (e.g. Freelancer) still show."
        ),
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
    if exclude_full_time:
        # "Not full-time" = part_time or unknown. IS DISTINCT FROM treats a NULL
        # workload as not-full_time (unlike !=), so workload-less gigs (e.g.
        # Freelancer, which reports no weekly hours) stay in the part-time lens.
        stmt = stmt.where(Job.workload.is_distinct_from("full_time"))
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


# Keep a tailored CV's label readable when a posting has a very long title.
_TAILORED_LABEL_TITLE_CAP = 80


def _tailored_cv_label(job: Job) -> str:
    """A human label for a job's tailored CV, e.g. 'Tailored — Weekend React gig'."""
    title = (job.title or "").strip() or f"job {job.id}"
    if len(title) > _TAILORED_LABEL_TITLE_CAP:
        title = title[:_TAILORED_LABEL_TITLE_CAP].rstrip() + "…"
    return f"Tailored — {title}"


def _resolve_base_cv(db: Session, base_cv_id: int | None) -> Cv:
    """Return the base/master CV to tailor from, or raise a clear HTTP error.

    With ``base_cv_id``: it must exist (404) and be a base CV — ``job_id`` IS NULL
    (422) — not an already-tailored variant. Without it: the most recently created
    base CV, or 400 if none exists yet (the DoD's 'clear error if no base CV').
    """
    if base_cv_id is not None:
        cv = db.get(Cv, base_cv_id)
        if cv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Base CV not found."
            )
        if cv.job_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"CV {base_cv_id} is tailored for job {cv.job_id}, not a base CV.",
            )
        return cv

    cv = db.scalars(
        select(Cv)
        .where(Cv.job_id.is_(None))
        .order_by(Cv.created_at.desc(), Cv.id.desc())
        .limit(1)
    ).first()
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No base CV found. Create a base CV (a CV with no job_id) before tailoring.",
        )
    return cv


@router.post(
    "/{job_id}/tailor-cv",
    response_model=TailorCvResponse,
    status_code=status.HTTP_201_CREATED,
)
def tailor_job_cv(
    job_id: int,
    payload: TailorCvRequest | None = None,
    db: Session = Depends(get_db),
) -> TailorCvResponse:
    """Tailor the base/master CV to a job and save it as a tailored ``cv`` row.

    Reads a base CV (``base_cv_id`` from the body if given, else the newest base CV
    — a CV with no ``job_id``), runs the AI ``tailor_cv`` feature (Claude, structured
    markdown), and persists the result as a new ``cv`` row with ``job_id`` set. The
    call is logged to ``ai_run``.

    Everything that can be rejected cheaply is checked *before* the paid AI call:
    404 if the job is unknown, 400 if no base CV exists yet, and 404 / 422 if a
    given ``base_cv_id`` is missing or is not a base CV. A missing API key returns
    503 and an upstream failure 502 (both handled centrally); on either AI error
    nothing is saved.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    base_cv = _resolve_base_cv(db, payload.base_cv_id if payload else None)

    tailored = tailor_cv(db, base_cv, job)

    cv = Cv(label=_tailored_cv_label(job), content=tailored.content, job_id=job.id)
    db.add(cv)
    db.commit()
    db.refresh(cv)

    return TailorCvResponse(
        job_id=job.id,
        cv_id=cv.id,
        base_cv_id=base_cv.id,
        label=cv.label,
        content=cv.content,
        model=tailored.result.model,
        cost_usd=tailored.result.cost_usd,
        run_id=tailored.result.run.id,
    )


def _resolve_proposal_cv(db: Session, job: Job, cv_id: int | None) -> Cv | None:
    """Choose the CV to ground a proposal in, or ``None`` to draft without one.

    With ``cv_id``: it must exist (404); any CV is allowed — a base CV or one
    already tailored for this job. Without it, auto-pick the most useful CV: the
    newest CV tailored for THIS job (from ``tailor_cv``), else the newest base CV,
    else ``None``. Unlike tailoring — which needs a base CV — a proposal can be
    drafted with no CV at all, so a missing CV is not an error here.
    """
    if cv_id is not None:
        cv = db.get(Cv, cv_id)
        if cv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found.")
        return cv

    # Prefer a CV already tailored for this job; fall back to the newest base CV.
    tailored = db.scalars(
        select(Cv)
        .where(Cv.job_id == job.id)
        .order_by(Cv.created_at.desc(), Cv.id.desc())
        .limit(1)
    ).first()
    if tailored is not None:
        return tailored

    return db.scalars(
        select(Cv)
        .where(Cv.job_id.is_(None))
        .order_by(Cv.created_at.desc(), Cv.id.desc())
        .limit(1)
    ).first()


@router.post(
    "/{job_id}/draft-proposal",
    response_model=DraftProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def draft_job_proposal(
    job_id: int,
    payload: DraftProposalRequest | None = None,
    db: Session = Depends(get_db),
) -> DraftProposalResponse:
    """Draft a proposal for a job and save it as an editable ``proposal`` row.

    Grounds the proposal in a CV (``cv_id`` from the body if given, else the CV
    already tailored for this job, else the newest base CV, else none), runs the AI
    ``draft_proposal`` feature (Claude, markdown prose), and persists the result as
    a new ``proposal`` row — editable afterward via the proposal endpoints. The
    call is logged to ``ai_run``.

    JobDesk NEVER submits: this only drafts. The proposal is reviewed, edited, and
    applied manually on the platform.

    404 if the job (or a given ``cv_id``) is unknown — both checked before the paid
    AI call. A missing API key returns 503 and an upstream failure 502 (both handled
    centrally); on either AI error nothing is saved.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    cv = _resolve_proposal_cv(db, job, payload.cv_id if payload else None)

    drafted = draft_proposal(db, job, cv)

    proposal = Proposal(job_id=job.id, content=drafted.content)
    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    return DraftProposalResponse(
        job_id=job.id,
        proposal_id=proposal.id,
        cv_id=cv.id if cv is not None else None,
        content=proposal.content,
        model=drafted.result.model,
        cost_usd=drafted.result.cost_usd,
        run_id=drafted.result.run.id,
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
