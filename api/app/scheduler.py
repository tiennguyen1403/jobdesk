"""In-process polling scheduler — an APScheduler ``BackgroundScheduler``.

Local-first: the poll loop lives inside the ``api`` container, not a separate
worker. It is started from the FastAPI ``lifespan`` (``app.main``) and, on a
``POLL_INTERVAL_MINUTES`` interval, runs :func:`app.services.poller.poll_enabled_searches`
to poll every enabled saved search.

``BackgroundScheduler`` (not ``AsyncIOScheduler``) on purpose: the poll job is
fully synchronous (SQLAlchemy + httpx), so running it in the scheduler's own
thread pool keeps it off the API event loop — the app stays responsive while a
cycle is in flight.

Double-start guard — what the DoD asks for. Under ``uvicorn --reload`` only the
single child worker imports the app and runs the lifespan (the reloader parent
just watches files), so startup fires once and the scheduler starts once. This
module makes that a guarantee regardless: the scheduler is a module-level
singleton and :func:`start_scheduler` is idempotent (a no-op once it is running)
and gated by ``POLL_ENABLED``, so no arrangement of reload/repeated-startup can
spin up a second loop in this process. (A multi-*process* deployment — e.g.
``--workers N`` — would need an external lock; out of scope for this local-first,
single-process app.)
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings

log = logging.getLogger("app.scheduler")

# Stable id so a re-add replaces rather than duplicates the poll job.
_JOB_ID = "poll_saved_searches"

# The process-wide singleton. None until started; reset to None on shutdown.
_scheduler: BackgroundScheduler | None = None


def _run_poll_cycle() -> None:
    """The scheduled tick — imported lazily so importing this module stays cheap."""
    from .services.poller import poll_enabled_searches

    poll_enabled_searches()


def start_scheduler() -> None:
    """Start the poll scheduler, unless disabled or already running.

    No-op when ``POLL_ENABLED`` is false, and idempotent when true (see the module
    docstring on the ``--reload`` guard). Safe to call from the FastAPI lifespan.
    """
    global _scheduler

    if not settings.poll_enabled:
        log.info("Polling disabled (POLL_ENABLED is false); scheduler not started.")
        return

    if _scheduler is not None and _scheduler.running:
        # Already started in this process — never spin up a second loop.
        return

    minutes = max(1, settings.poll_interval_minutes)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_poll_cycle,
        trigger="interval",
        minutes=minutes,
        id=_JOB_ID,
        replace_existing=True,
        # A slow cycle must not stack up: run at most one at a time and collapse
        # any fires missed while the previous one was still running.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("Polling scheduler started (every %d min).", minutes)


def shutdown_scheduler() -> None:
    """Stop the scheduler if running — called from the lifespan on shutdown."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Polling scheduler stopped.")
    _scheduler = None
