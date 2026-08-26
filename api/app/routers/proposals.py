from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, Proposal
from ..schemas.proposal import ProposalCreate, ProposalRead, ProposalUpdate

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _ensure_job_exists(db: Session, job_id: int) -> None:
    """A proposal must reference a real job. Checking here turns what would be an
    IntegrityError on commit into a clean 404.
    """
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")


@router.post("", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
def create_proposal(payload: ProposalCreate, db: Session = Depends(get_db)) -> Proposal:
    """Store a proposal draft for a job.

    Pure storage — drafting the text with Claude is a separate Phase 2 step, and
    JobDesk never auto-submits: the draft is applied manually on the platform.
    """
    _ensure_job_exists(db, payload.job_id)

    proposal = Proposal(**payload.model_dump())
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.get("", response_model=list[ProposalRead])
def list_proposals(
    db: Session = Depends(get_db),
    job_id: int | None = Query(
        default=None, description="Keep only proposals drafted for this job."
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Proposal]:
    """List proposals, newest first. Narrow to one job's drafts with ``job_id``."""
    stmt = select(Proposal)
    if job_id is not None:
        stmt = stmt.where(Proposal.job_id == job_id)
    stmt = (
        stmt.order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


@router.get("/{proposal_id}", response_model=ProposalRead)
def get_proposal(proposal_id: int, db: Session = Depends(get_db)) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found."
        )
    return proposal


@router.patch("/{proposal_id}", response_model=ProposalRead)
def update_proposal(
    proposal_id: int, payload: ProposalUpdate, db: Session = Depends(get_db)
) -> Proposal:
    """Edit a proposal's content. Only keys present in the body change; editing
    ``content`` bumps ``updated_at`` (managed by the ORM).
    """
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found."
        )

    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(proposal, field, value)

    db.commit()
    db.refresh(proposal)
    return proposal


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal(proposal_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a proposal draft."""
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found."
        )

    db.delete(proposal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
