"""Browser-capture ingestion: ``POST /api/capture``.

The zero-approval path — a bookmarklet (``docs/capture-bookmarklet.md``) scrapes
the Upwork job page the user is viewing and POSTs it here. The payload is routed
through :class:`~app.providers.capture.CaptureProvider` (normalize + derive the
dedupe id) and the shared ingestion service (upsert/dedupe), so a captured job
behaves exactly like one from any other source and re-capturing never duplicates
a row. Ingested jobs land in the Inbox — no pipeline card is opened.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Job
from ..providers import CaptureProvider
from ..schemas.capture import CapturePayload, CaptureResult
from ..schemas.job import JobRead
from ..services import ingest_jobs

router = APIRouter(prefix="/capture", tags=["capture"])

# The capture provider is stateless, so a single shared instance is enough.
_provider = CaptureProvider()


@router.post("", response_model=CaptureResult)
def capture(payload: CapturePayload, db: Session = Depends(get_db)) -> CaptureResult:
    """Normalize a scraped posting, ingest it (deduped), and return the summary.

    ``mode="json"`` makes the payload JSON-native (datetimes → ISO strings) so the
    verbatim copy kept in the JSONB ``raw`` column is serializable.
    """
    normalized = _provider.fetch(payload.model_dump(mode="json"))
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No job captured (a URL is required).",
        )

    summary = ingest_jobs(db, _provider.key, normalized)
    db.commit()

    jobs: list[JobRead] = []
    if summary.affected_ids:
        rows = db.scalars(
            select(Job)
            .where(Job.id.in_(summary.affected_ids))
            .options(selectinload(Job.application))
        ).all()
        jobs = [JobRead.model_validate(row) for row in rows]

    return CaptureResult(
        source=summary.source,
        created=summary.created,
        updated=summary.updated,
        skipped=summary.skipped,
        job_ids=summary.affected_ids,
        jobs=jobs,
    )
