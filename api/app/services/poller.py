"""Poll saved searches → provider → the shared ingestion service.

The capstone of the Upwork connector: JobDesk has no webhooks (the Upwork API is
poll-only), so enabled :class:`~app.models.SavedSearch` rows are run on a schedule
(``app.scheduler``) and, on demand, by ``POST /api/saved-searches/{id}/run``. Both
paths funnel through here.

One search runs as: resolve its provider → ``provider.fetch(search.query)`` →
hand the batch to the provider-agnostic ingestion service (upsert/dedupe by
``(source, external_id)``) → stamp ``last_polled_at``. Ingested jobs land in the
Inbox; JobDesk never opens a pipeline card and never auto-applies.

Two callers, two error stances — deliberately:

* **Manual run** (:func:`run_saved_search`) lets provider errors propagate, so a
  human clicking "run now" while Upwork is disconnected gets a real 503/502 (via
  the app's exception handlers) rather than a silent all-zero summary.
* **Scheduled cycle** (:func:`poll_searches`) isolates each search: a provider
  error — most commonly "Upwork isn't connected" — becomes a *logged no-op* and
  the cycle moves on, so one bad search never wedges the scheduler.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import SavedSearch
from ..providers import JobProvider, UpworkProvider
from .ingest import IngestSummary, ingest_jobs
from .upwork_oauth import UpworkError

log = logging.getLogger("app.poller")


class PollError(RuntimeError):
    """A saved search cannot be polled — e.g. its provider is unknown/not pollable."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _provider_for(search: SavedSearch, db: Session) -> JobProvider:
    """Resolve the provider a saved search runs against.

    Only Upwork is pollable today; the registry is a dict so a second polled
    source drops in without touching callers. A stateful provider (Upwork reads
    the stored OAuth token) is built per call with the session.
    """
    if search.provider == UpworkProvider.key:
        return UpworkProvider(db)
    raise PollError(
        f"Saved search {search.id} uses provider {search.provider!r}, "
        "which cannot be polled."
    )


def run_saved_search(db: Session, search: SavedSearch) -> IngestSummary:
    """Poll one saved search now: fetch → ingest → stamp ``last_polled_at``, commit.

    Returns the :class:`~app.services.ingest.IngestSummary` (created/updated/skipped
    + affected ids). Provider errors (Upwork unconfigured/not connected) propagate;
    the manual endpoint surfaces them, the scheduler catches them (see the module
    docstring). ``last_polled_at`` is stamped only on a successful fetch, so it
    tracks the last *successful* poll — a failed attempt leaves it untouched.
    """
    provider = _provider_for(search, db)
    normalized = provider.fetch(search.query or {})
    summary = ingest_jobs(db, provider.key, normalized)
    search.last_polled_at = _now()
    db.commit()
    log.info(
        "Polled saved search %d (%s): created=%d updated=%d skipped=%d",
        search.id,
        search.name,
        summary.created,
        summary.updated,
        summary.skipped,
    )
    return summary


@dataclass
class PollRun:
    """The outcome of polling one saved search within a cycle.

    ``summary`` is set when the run succeeded; when it no-op'd (provider error /
    non-pollable) ``summary`` is ``None`` and ``skipped_reason`` explains why.
    """

    search_id: int
    name: str
    provider: str
    summary: IngestSummary | None = None
    skipped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.summary is not None


def poll_searches(db: Session, *, provider: str | None = None) -> list[PollRun]:
    """Run every enabled saved search once, isolating failures per search.

    A provider error (typically "Upwork isn't connected") or any unexpected
    exception is caught, the session rolled back, and the search recorded as a
    logged no-op — so a single failure never aborts the cycle or the scheduler.
    Optionally restrict to one ``provider``.
    """
    stmt = select(SavedSearch).where(SavedSearch.enabled.is_(True))
    if provider is not None:
        stmt = stmt.where(SavedSearch.provider == provider)
    stmt = stmt.order_by(SavedSearch.id)
    searches = db.scalars(stmt).all()

    runs: list[PollRun] = []
    for search in searches:
        try:
            summary = run_saved_search(db, search)
            runs.append(PollRun(search.id, search.name, search.provider, summary=summary))
        except (UpworkError, PollError) as exc:
            # Expected, recoverable no-ops (not connected / not pollable): info-level.
            db.rollback()
            log.info(
                "Poll no-op for saved search %d (%s): %s", search.id, search.name, exc
            )
            runs.append(
                PollRun(search.id, search.name, search.provider, skipped_reason=str(exc))
            )
        except Exception as exc:  # one bad search must not kill the cycle
            db.rollback()
            log.exception("Poll failed for saved search %d (%s)", search.id, search.name)
            runs.append(
                PollRun(search.id, search.name, search.provider, skipped_reason=str(exc))
            )

    ran = [r for r in runs if r.ok]
    log.info(
        "Poll cycle complete: %d search(es), %d ran, %d skipped, created=%d updated=%d",
        len(runs),
        len(ran),
        len(runs) - len(ran),
        sum(r.summary.created for r in ran),
        sum(r.summary.updated for r in ran),
    )
    return runs


def poll_enabled_searches() -> list[PollRun]:
    """Scheduler entry point: open a fresh session, poll all enabled searches, close.

    The scheduled job runs in a background thread with no request context, so it
    owns its own :class:`~sqlalchemy.orm.Session` (the request-scoped ``get_db``
    dependency isn't available here).
    """
    db = SessionLocal()
    try:
        return poll_searches(db)
    finally:
        db.close()
