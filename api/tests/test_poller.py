"""Polling scheduler + on-demand run — hermetic.

No network reaches Upwork: the provider is a seam (``poller._provider_for``) that
the tests swap for a stub returning canned :class:`NormalizedJob`\\ s. Coverage
mirrors the issue's DoD:

* ``POST /api/saved-searches/{id}/run`` ingests via the shared ingestion service,
  dedupes on a second run, and stamps ``last_polled_at``.
* the scheduled cycle (:func:`poller.poll_searches`) iterates only *enabled*
  searches and turns a provider error (e.g. Upwork not connected) into a logged
  no-op instead of raising.
* the scheduler is off unless ``POLL_ENABLED`` is set, and starting it twice
  never spins up a second loop (the ``--reload`` guard).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import scheduler
from app.config import settings
from app.models import Job, SavedSearch
from app.providers import FreelancerProvider, JobProvider, NormalizedJob, UpworkProvider
from app.services import poller
from app.services.freelancer_oauth import FreelancerServiceError
from app.services.upwork_oauth import UpworkServiceError


# --- stubs -------------------------------------------------------------------


class _StubProvider(JobProvider):
    """A pollable provider that returns canned jobs (or raises) — no network."""

    key = "upwork"  # the ingest source; matches the real Upwork provider's key

    def __init__(self, jobs: list[NormalizedJob] | None = None, *, error: Exception | None = None):
        self._jobs = jobs or []
        self._error = error

    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _use_provider(monkeypatch, provider: JobProvider) -> None:
    """Route every poll through ``provider`` instead of the real Upwork one."""
    monkeypatch.setattr(poller, "_provider_for", lambda search, db: provider)


def _nj(external_id: str, **overrides) -> NormalizedJob:
    """A valid part-time NormalizedJob for ``external_id``."""
    data = dict(
        external_id=external_id,
        url=f"https://www.upwork.com/jobs/{external_id}",
        title="Weekend Python gig",
        description="Evenings & weekends only.",
        budget_type="hourly",
        budget_min=30.0,
        budget_max=60.0,
        workload="part_time",
        weekly_hours=10,
    )
    data.update(overrides)
    return NormalizedJob(**data)


def _make_search(db, **overrides) -> SavedSearch:
    data = dict(name="Evening Python gigs", provider="upwork", query={"keywords": "python"})
    data.update(overrides)
    search = SavedSearch(**data)
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


def _jobs(db, ext_ids, source: str = "upwork") -> list[Job]:
    """Rows for these external_ids — scoped so a populated dev DB can't skew counts."""
    from sqlalchemy import select

    return list(
        db.scalars(
            select(Job).where(Job.source == source, Job.external_id.in_(list(ext_ids)))
        )
    )


# --- POST /{id}/run: ingest, dedupe, stamp (the DoD's core) ------------------


def test_run_now_ingests_via_ingestion_service(client: TestClient, db_session, monkeypatch) -> None:
    search = _make_search(db_session)
    _use_provider(monkeypatch, _StubProvider([_nj("u1"), _nj("u2")]))

    before = datetime.now(timezone.utc)
    resp = client.post(f"/api/saved-searches/{search.id}/run")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["created"], body["updated"], body["skipped"]) == (2, 0, 0)
    assert body["search_id"] == search.id
    assert body["provider"] == "upwork"
    assert len(body["job_ids"]) == 2

    # The jobs actually landed via the shared ingestion service (source = upwork).
    rows = _jobs(db_session, {"u1", "u2"})
    assert {r.external_id for r in rows} == {"u1", "u2"}
    assert set(body["job_ids"]) == {r.id for r in rows}

    # last_polled_at was stamped fresh.
    assert body["last_polled_at"] is not None
    db_session.expire(search)
    assert search.last_polled_at is not None
    assert search.last_polled_at >= before


def test_run_now_dedupes_on_rerun(client: TestClient, db_session, monkeypatch) -> None:
    search = _make_search(db_session)
    _use_provider(monkeypatch, _StubProvider([_nj("u1"), _nj("u2")]))

    first = client.post(f"/api/saved-searches/{search.id}/run").json()
    second = client.post(f"/api/saved-searches/{search.id}/run").json()

    assert (first["created"], first["updated"]) == (2, 0)
    # Re-running the same search updates the same rows — no duplicates.
    assert (second["created"], second["updated"]) == (0, 2)
    assert set(second["job_ids"]) == set(first["job_ids"])
    assert len(_jobs(db_session, {"u1", "u2"})) == 2


def test_run_now_ingested_jobs_open_no_card(client: TestClient, db_session, monkeypatch) -> None:
    search = _make_search(db_session)
    _use_provider(monkeypatch, _StubProvider([_nj("u1")]))

    body = client.post(f"/api/saved-searches/{search.id}/run").json()

    # Inbox model: a polled job lists but opens no pipeline card, and never auto-applies.
    for job_id in body["job_ids"]:
        assert db_session.get(Job, job_id).application is None
    listed = {j["id"]: j for j in client.get("/api/jobs").json()}
    for job_id in body["job_ids"]:
        assert listed[job_id]["application"] is None


def test_run_now_missing_search_is_404(client: TestClient) -> None:
    assert client.post("/api/saved-searches/999999/run").status_code == 404


def test_run_now_non_pollable_provider_is_422(client: TestClient, db_session) -> None:
    # A manual-entry saved search has no pollable provider → a clean 422, not a 500.
    search = _make_search(db_session, provider="manual")
    resp = client.post(f"/api/saved-searches/{search.id}/run")
    assert resp.status_code == 422, resp.text
    assert "cannot be polled" in resp.json()["detail"]


def test_run_now_not_connected_surfaces_502(client: TestClient, db_session, monkeypatch) -> None:
    # A human trigger while Upwork is disconnected gets a real error, not a fake no-op.
    search = _make_search(db_session)
    _use_provider(monkeypatch, _StubProvider(error=UpworkServiceError("not connected")))
    assert client.post(f"/api/saved-searches/{search.id}/run").status_code == 502


# --- provider registry: which providers a saved search can be polled against --


def test_provider_for_resolves_pollable_providers(db_session) -> None:
    # The real registry (not the test stub) routes each provider name to its class.
    upwork = _make_search(db_session, provider="upwork")
    freelancer = _make_search(db_session, provider="freelancer")

    assert isinstance(poller._provider_for(upwork, db_session), UpworkProvider)
    assert isinstance(poller._provider_for(freelancer, db_session), FreelancerProvider)


def test_provider_for_unknown_provider_raises_poll_error(db_session) -> None:
    search = _make_search(db_session, provider="manual")
    with pytest.raises(poller.PollError):
        poller._provider_for(search, db_session)


# --- part-time scope enforced at the ingest choke point ----------------------


def test_run_now_never_ingests_full_time_jobs(client: TestClient, db_session, monkeypatch) -> None:
    # HARD rule: even if a posting comes back full-time, the poll drops it before
    # ingest — nothing full-time is ever tracked.
    search = _make_search(db_session)
    _use_provider(
        monkeypatch,
        _StubProvider([_nj("pt1"), _nj("ft1", workload="full_time", weekly_hours=40)]),
    )

    body = client.post(f"/api/saved-searches/{search.id}/run").json()

    assert (body["created"], body["updated"]) == (1, 0)  # only the part-time one
    assert {r.external_id for r in _jobs(db_session, {"pt1", "ft1"})} == {"pt1"}


def test_run_now_honors_max_weekly_hours_cap(client: TestClient, db_session, monkeypatch) -> None:
    # A search capped at 15 h/week must drop a 40 h/week posting at ingest.
    search = _make_search(db_session, query={"keywords": "python", "max_weekly_hours": 15})
    _use_provider(
        monkeypatch,
        _StubProvider([_nj("ok", weekly_hours=10), _nj("over", weekly_hours=40)]),
    )

    body = client.post(f"/api/saved-searches/{search.id}/run").json()

    assert (body["created"], body["updated"]) == (1, 0)
    assert {r.external_id for r in _jobs(db_session, {"ok", "over"})} == {"ok"}


# --- scheduled cycle: enabled-only, error-isolated ---------------------------


def test_poll_searches_runs_only_enabled(db_session, monkeypatch) -> None:
    enabled = _make_search(db_session, name="on", query={"keywords": "python"})
    disabled = _make_search(db_session, name="off", enabled=False)
    _use_provider(monkeypatch, _StubProvider([_nj("u1")]))

    runs = poller.poll_searches(db_session)

    ran_ids = {r.search_id for r in runs if r.ok}
    assert enabled.id in ran_ids
    assert disabled.id not in ran_ids  # the poll loop skips disabled searches
    db_session.expire(disabled)
    assert disabled.last_polled_at is None  # never polled


def test_poll_searches_provider_error_is_a_noop(db_session, monkeypatch) -> None:
    search = _make_search(db_session)
    _use_provider(monkeypatch, _StubProvider(error=UpworkServiceError("not connected")))

    # A provider error must NOT propagate — the cycle logs a no-op and carries on.
    runs = poller.poll_searches(db_session)

    assert len(runs) == 1
    assert runs[0].ok is False
    assert runs[0].summary is None
    assert "not connected" in runs[0].skipped_reason
    # Nothing ingested, and the failed attempt left last_polled_at untouched.
    assert _jobs(db_session, {"u1", "u2"}) == []
    db_session.expire(search)
    assert search.last_polled_at is None


def test_poll_searches_freelancer_error_is_a_noop(db_session, monkeypatch) -> None:
    # A Freelancer provider error is an expected no-op too (info-level, cycle carries
    # on) — not the noisy generic-exception path.
    search = _make_search(db_session, provider="freelancer")
    _use_provider(monkeypatch, _StubProvider(error=FreelancerServiceError("not connected")))

    runs = poller.poll_searches(db_session)

    assert len(runs) == 1
    assert runs[0].ok is False
    assert "not connected" in runs[0].skipped_reason
    db_session.expire(search)
    assert search.last_polled_at is None


# --- scheduler lifecycle: env-gated + idempotent (the --reload guard) --------


def test_scheduler_disabled_by_default_is_noop() -> None:
    # POLL_ENABLED is false by default → start is a no-op, nothing to shut down.
    assert settings.poll_enabled is False
    scheduler.start_scheduler()
    try:
        assert scheduler._scheduler is None
    finally:
        scheduler.shutdown_scheduler()


def test_scheduler_start_is_idempotent_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "poll_enabled", True)
    monkeypatch.setattr(settings, "poll_interval_minutes", 60)
    try:
        scheduler.start_scheduler()
        first = scheduler._scheduler
        assert first is not None and first.running
        # A second start (as a stray reload/startup would) reuses the same loop.
        scheduler.start_scheduler()
        assert scheduler._scheduler is first
        assert len(first.get_jobs()) == 1  # exactly one poll job, not two
    finally:
        scheduler.shutdown_scheduler()
    assert scheduler._scheduler is None
