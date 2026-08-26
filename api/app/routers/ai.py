from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import call_claude
from ..db import get_db
from ..models import AiRun
from ..schemas.ai import AiRunRead, SmokeRequest, SmokeResponse

router = APIRouter(prefix="/ai", tags=["ai"])

# A trivial prompt to exercise the whole path (client → cost logging → response).
_SMOKE_PROMPT = "Reply with exactly one word: pong."


@router.get("/runs", response_model=list[AiRunRead])
def list_runs(
    db: Session = Depends(get_db),
    feature: str | None = Query(default=None, description="Keep only runs of this AI feature."),
    status_filter: str | None = Query(
        default=None, alias="status", description="Keep only 'success' or 'error' runs."
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AiRun]:
    """List recent AI runs, newest first — the cost/usage ledger."""
    stmt = select(AiRun)
    if feature is not None:
        stmt = stmt.where(AiRun.feature == feature)
    if status_filter is not None:
        stmt = stmt.where(AiRun.status == status_filter)
    stmt = stmt.order_by(AiRun.created_at.desc(), AiRun.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


@router.post("/smoke", response_model=SmokeResponse)
def smoke(
    payload: SmokeRequest | None = None, db: Session = Depends(get_db)
) -> SmokeResponse:
    """Send one trivial prompt to Claude to verify the AI foundation end to end.

    Proves the whole path works: a missing key returns a clean 503, a real call
    returns the answer, and either way exactly one ``ai_run`` row is written. This
    is the only "feature" the foundation ships — real features arrive in Wave B.
    """
    prompt = payload.prompt if payload and payload.prompt else _SMOKE_PROMPT
    result = call_claude(db, feature="smoke", prompt=prompt)
    return SmokeResponse(
        text=result.text,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        run_id=result.run.id,
    )
