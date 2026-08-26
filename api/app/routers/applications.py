from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Application, ApplicationStatus
from ..schemas.application import ApplicationCard, ApplicationUpdate

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationCard])
def list_applications(
    db: Session = Depends(get_db),
    status_filter: ApplicationStatus | None = Query(
        default=None,
        alias="status",
        description="Keep only cards in this pipeline stage (a Kanban column).",
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Application]:
    """List pipeline cards, newest first, each embedding its job summary.

    This is the board feed: filter by ``status`` to fetch a single column, or
    omit it for every card across the funnel.
    """
    stmt = select(Application).options(selectinload(Application.job))
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter)
    stmt = (
        stmt.order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


@router.get("/{application_id}", response_model=ApplicationCard)
def get_application(application_id: int, db: Session = Depends(get_db)) -> Application:
    application = db.get(
        Application, application_id, options=[selectinload(Application.job)]
    )
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found."
        )
    return application


@router.patch("/{application_id}", response_model=ApplicationCard)
def update_application(
    application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> Application:
    """Move a card between stages or edit its notes / applied date.

    Only keys present in the body change. JobDesk never auto-applies — advancing
    a card to ``applied`` just records that you applied manually on the platform.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found."
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)

    db.commit()
    db.refresh(application)
    return application
