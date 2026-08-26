"""Provider-agnostic ingestion: persist a batch of NormalizedJob, deduped.

Every job source (browser capture, the Upwork poller, ...) normalizes its
postings to :class:`~app.providers.base.NormalizedJob` and hands the batch to
:func:`ingest_jobs` — one shared upsert/dedupe write-path instead of each
provider rolling its own. Postings dedupe by ``(source, external_id)``, matching
the ``uq_job_source_external_id`` constraint on :class:`~app.models.Job`.

Contract:

* **Dedupe key** is ``(source, external_id)``: a new key inserts a row, a known
  key updates that row in place, so re-ingesting an identical batch creates no
  duplicates (idempotent).
* **external_id is required here.** A job without one is *skipped*: manual
  entries carry ``external_id=NULL``, which Postgres treats as distinct, so they
  can't be deduped and don't belong on this provider path (add them via
  ``POST /api/jobs`` instead).
* **No pipeline card.** Ingested jobs land in the Inbox — they show up in
  ``GET /api/jobs`` but do **not** auto-open an :class:`~app.models.Application`.
  JobDesk never auto-applies; a card is opened explicitly later.
* **Non-posting columns are preserved.** An update overwrites only the
  NormalizedJob-derived fields; a job's AI ``match_*`` score and ``created_at``
  survive a re-ingest, so the poller refreshing a posting never wipes its score.
* **The caller owns the transaction.** This flushes (to assign PKs and to dedupe
  within the surrounding transaction) but does not commit — mirroring the AI
  layer, the endpoint / poller commits.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job
from ..providers import NormalizedJob


@dataclass
class IngestSummary:
    """What one :func:`ingest_jobs` batch did — for logs and API responses.

    ``created`` / ``updated`` derive from the id lists so the counts can't drift
    from the ids. ``affected_ids`` is created + updated (a skipped input has no
    id — it was never inserted). ``skipped`` counts inputs with no usable
    ``external_id``.
    """

    source: str
    created_ids: list[int] = field(default_factory=list)
    updated_ids: list[int] = field(default_factory=list)
    skipped: int = 0

    @property
    def created(self) -> int:
        return len(self.created_ids)

    @property
    def updated(self) -> int:
        return len(self.updated_ids)

    @property
    def affected_ids(self) -> list[int]:
        return [*self.created_ids, *self.updated_ids]

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped


def _apply(job: Job, normalized: NormalizedJob) -> None:
    """Copy a posting's fields onto an existing row, in place.

    Only NormalizedJob-derived fields are written, so columns computed elsewhere
    — the AI ``match_*`` score, ``created_at`` — are left intact on a re-ingest.
    """
    for name, value in normalized.model_dump().items():
        setattr(job, name, value)


def ingest_jobs(db: Session, source: str, jobs: list[NormalizedJob]) -> IngestSummary:
    """Upsert a batch of normalized jobs for ``source``, deduped by external_id.

    Returns an :class:`IngestSummary` (created / updated / skipped counts and the
    affected job ids). See the module docstring for the full contract.
    """
    # Collapse within-batch duplicates by external_id (last occurrence wins) and
    # drop inputs with no usable external_id — they can't be deduped on this path.
    by_external_id: dict[str, NormalizedJob] = {}
    skipped = 0
    for normalized in jobs:
        external_id = normalized.external_id
        if external_id is None or not external_id.strip():
            skipped += 1
            continue
        by_external_id[external_id] = normalized

    created_rows: list[Job] = []
    updated_rows: list[Job] = []
    if by_external_id:
        # One query resolves which of these already exist for this source.
        existing_rows = db.scalars(
            select(Job).where(
                Job.source == source,
                Job.external_id.in_(by_external_id.keys()),
            )
        ).all()
        existing = {row.external_id: row for row in existing_rows}

        for external_id, normalized in by_external_id.items():
            row = existing.get(external_id)
            if row is None:
                row = Job(source=source, **normalized.model_dump())
                db.add(row)
                created_rows.append(row)
            else:
                _apply(row, normalized)
                updated_rows.append(row)

        # Flush so new rows get their PKs and updates hit the DB inside the
        # caller's transaction; the caller commits.
        db.flush()

    return IngestSummary(
        source=source,
        created_ids=[row.id for row in created_rows],
        updated_ids=[row.id for row in updated_rows],
        skipped=skipped,
    )
