from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Cv, Job
from ..schemas.cv import CvCreate, CvRead, CvUpdate

router = APIRouter(prefix="/cvs", tags=["cvs"])


def _ensure_job_exists(db: Session, job_id: int | None) -> None:
    """Guard a CV's ``job_id``: if set, it must reference a real job.

    NULL is always valid (a base/master CV). Checking here turns what would be an
    IntegrityError on commit into a clean 404.
    """
    if job_id is not None and db.get(Job, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")


@router.post("", response_model=CvRead, status_code=status.HTTP_201_CREATED)
def create_cv(payload: CvCreate, db: Session = Depends(get_db)) -> Cv:
    """Store a CV. A NULL ``job_id`` creates a base/master CV; a set ``job_id``
    files it as a tailored variant for that job.

    Pure storage — tailoring content with Claude is a separate Phase 2 step.
    """
    _ensure_job_exists(db, payload.job_id)

    cv = Cv(**payload.model_dump())
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv


@router.get("", response_model=list[CvRead])
def list_cvs(
    db: Session = Depends(get_db),
    job_id: int | None = Query(
        default=None, description="Keep only CVs tailored for this job."
    ),
    base_only: bool = Query(
        default=False,
        description=(
            "Keep only base/master CVs (job_id IS NULL). Takes precedence over "
            "job_id if both are given."
        ),
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Cv]:
    """List CVs, newest first. Narrow to one job's tailored CVs with ``job_id``,
    or to the reusable base CVs with ``base_only``.
    """
    stmt = select(Cv)
    if base_only:
        stmt = stmt.where(Cv.job_id.is_(None))
    elif job_id is not None:
        stmt = stmt.where(Cv.job_id == job_id)
    stmt = stmt.order_by(Cv.created_at.desc(), Cv.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


@router.get("/{cv_id}", response_model=CvRead)
def get_cv(cv_id: int, db: Session = Depends(get_db)) -> Cv:
    cv = db.get(Cv, cv_id)
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found.")
    return cv


@router.patch("/{cv_id}", response_model=CvRead)
def update_cv(cv_id: int, payload: CvUpdate, db: Session = Depends(get_db)) -> Cv:
    """Patch a CV's label / content, or re-file it under a different job (or NULL
    to make it a base CV). Only keys present in the body change.
    """
    cv = db.get(Cv, cv_id)
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found.")

    fields = payload.model_dump(exclude_unset=True)
    if "job_id" in fields:
        _ensure_job_exists(db, fields["job_id"])

    for field, value in fields.items():
        setattr(cv, field, value)

    db.commit()
    db.refresh(cv)
    return cv


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv(cv_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a CV."""
    cv = db.get(Cv, cv_id)
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found.")

    db.delete(cv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
