from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SavedSearch
from ..schemas.saved_search import (
    SavedSearchCreate,
    SavedSearchRead,
    SavedSearchRunResult,
    SavedSearchUpdate,
)
from ..services import poller

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])


@router.post("", response_model=SavedSearchRead, status_code=status.HTTP_201_CREATED)
def create_saved_search(
    payload: SavedSearchCreate, db: Session = Depends(get_db)
) -> SavedSearch:
    """Persist a reusable search definition for the poller (#6) to iterate.

    The part-time constraints (workload / max weekly hours) live in ``query`` so
    polling only pulls evenings-and-weekends-viable work. JobDesk never
    auto-applies — a saved search only finds work.
    """
    search = SavedSearch(**payload.model_dump())
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


@router.get("", response_model=list[SavedSearchRead])
def list_saved_searches(
    db: Session = Depends(get_db),
    provider: str | None = Query(
        default=None, description="Keep only searches for this provider."
    ),
    enabled: bool | None = Query(
        default=None, description="Filter by the enabled flag."
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SavedSearch]:
    """List saved searches, newest first. Optionally filter by provider/enabled."""
    stmt = select(SavedSearch)
    if provider is not None:
        stmt = stmt.where(SavedSearch.provider == provider)
    if enabled is not None:
        stmt = stmt.where(SavedSearch.enabled == enabled)
    stmt = (
        stmt.order_by(SavedSearch.created_at.desc(), SavedSearch.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


@router.get("/{search_id}", response_model=SavedSearchRead)
def get_saved_search(search_id: int, db: Session = Depends(get_db)) -> SavedSearch:
    search = db.get(SavedSearch, search_id)
    if search is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    return search


@router.patch("/{search_id}", response_model=SavedSearchRead)
def update_saved_search(
    search_id: int, payload: SavedSearchUpdate, db: Session = Depends(get_db)
) -> SavedSearch:
    """Edit a saved search. Only keys present in the body change; supplying
    ``query`` replaces it wholesale (not a deep merge).
    """
    search = db.get(SavedSearch, search_id)
    if search is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )

    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(search, field, value)

    db.commit()
    db.refresh(search)
    return search


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(search_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a saved search so the poller stops iterating it."""
    search = db.get(SavedSearch, search_id)
    if search is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )

    db.delete(search)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{search_id}/run", response_model=SavedSearchRunResult)
def run_saved_search_now(
    search_id: int, db: Session = Depends(get_db)
) -> SavedSearchRunResult:
    """Poll one saved search immediately and return the ingest summary.

    The manual counterpart to the scheduler — useful for testing without waiting a
    cycle. Runs regardless of the ``enabled`` flag (that gates only the scheduled
    loop). Ingested jobs land in the Inbox; JobDesk never auto-applies. When Upwork
    is unconfigured/not connected the underlying call raises, surfacing as a clean
    503/502 (via the app's exception handlers) rather than a silent no-op; a search
    whose provider can't be polled is a 422.
    """
    search = db.get(SavedSearch, search_id)
    if search is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )

    try:
        summary = poller.run_saved_search(db, search)
    except poller.PollError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return SavedSearchRunResult(
        search_id=search.id,
        provider=search.provider,
        created=summary.created,
        updated=summary.updated,
        skipped=summary.skipped,
        job_ids=summary.affected_ids,
        last_polled_at=search.last_polled_at,
    )
