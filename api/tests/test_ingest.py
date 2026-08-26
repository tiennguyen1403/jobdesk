"""Provider-agnostic ingestion: upsert + dedupe by (source, external_id).

Hermetic unit tests — they call ``ingest_jobs`` against the rolled-back
``db_session`` fixture, no network to any provider. Coverage: a fresh insert, an
exact re-ingest (idempotent dedupe), a partial update in place, the skip path for
jobs without an external_id, within-batch de-duplication, per-source scoping,
preservation of an AI score across a re-ingest, and the Inbox rule — an ingested
job opens no pipeline card yet still lists in the API.
"""
from sqlalchemy import select

from app.models import Job
from app.providers import NormalizedJob
from app.services import ingest_jobs


def _nj(external_id: str | None, **overrides) -> NormalizedJob:
    """A valid part-time NormalizedJob for ``external_id``; override any field."""
    data = dict(
        external_id=external_id,
        url=f"https://upwork.test/jobs/{external_id or 'na'}",
        title="Weekend React gig",
        description="Evenings & weekends only.",
        budget_type="hourly",
        budget_min=30.0,
        budget_max=50.0,
        workload="part_time",
        weekly_hours=10,
        duration="one_to_three_months",
        skills=["react", "typescript"],
    )
    data.update(overrides)
    return NormalizedJob(**data)


def _rows(db, source: str) -> list[Job]:
    return list(db.scalars(select(Job).where(Job.source == source)))


def test_fresh_insert(db_session) -> None:
    summary = ingest_jobs(db_session, "upwork", [_nj("u1"), _nj("u2")])

    assert summary.created == 2
    assert summary.updated == 0
    assert summary.skipped == 0
    assert len(summary.affected_ids) == 2

    rows = _rows(db_session, "upwork")
    assert {r.external_id for r in rows} == {"u1", "u2"}
    assert all(r.source == "upwork" for r in rows)
    assert all(r.id in summary.created_ids for r in rows)


def test_exact_reingest_is_idempotent(db_session) -> None:
    batch = [_nj("u1"), _nj("u2")]
    first = ingest_jobs(db_session, "upwork", batch)
    second = ingest_jobs(db_session, "upwork", batch)

    # The second pass updates the same rows — it never inserts duplicates.
    assert first.created == 2
    assert second.created == 0
    assert second.updated == 2
    assert set(second.affected_ids) == set(first.affected_ids)
    assert len(_rows(db_session, "upwork")) == 2


def test_partial_update_in_place(db_session) -> None:
    created = ingest_jobs(db_session, "upwork", [_nj("u1", title="Old", weekly_hours=10)])
    job_id = created.created_ids[0]

    updated = ingest_jobs(
        db_session, "upwork", [_nj("u1", title="New", weekly_hours=8, budget_max=99.0)]
    )

    assert updated.created == 0
    assert updated.updated == 1
    assert updated.updated_ids == [job_id]  # same row, updated in place

    rows = _rows(db_session, "upwork")
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "New"
    assert row.weekly_hours == 8
    assert row.budget_max == 99.0


def test_missing_external_id_is_skipped(db_session) -> None:
    summary = ingest_jobs(db_session, "upwork", [_nj("u1"), _nj(None), _nj("   ")])

    assert summary.created == 1
    assert summary.skipped == 2  # None and a blank/whitespace id can't be deduped
    rows = _rows(db_session, "upwork")
    assert len(rows) == 1
    assert rows[0].external_id == "u1"


def test_within_batch_duplicate_collapses(db_session) -> None:
    # The same external_id twice in one batch is one row; the last occurrence wins.
    summary = ingest_jobs(
        db_session, "upwork", [_nj("u1", title="First"), _nj("u1", title="Last")]
    )

    assert summary.created == 1
    assert summary.updated == 0
    rows = _rows(db_session, "upwork")
    assert len(rows) == 1
    assert rows[0].title == "Last"


def test_source_scopes_the_dedupe_key(db_session) -> None:
    # Same external_id under two sources are distinct rows: the key is (source, id).
    a = ingest_jobs(db_session, "upwork", [_nj("42")])
    b = ingest_jobs(db_session, "capture", [_nj("42")])

    assert a.created == 1
    assert b.created == 1
    assert a.created_ids != b.created_ids
    assert len(_rows(db_session, "upwork")) == 1
    assert len(_rows(db_session, "capture")) == 1


def test_update_preserves_match_score(db_session) -> None:
    # A prior score_match wrote match_* on the row; re-ingesting must not wipe it.
    created = ingest_jobs(db_session, "upwork", [_nj("u1", title="Old")])
    job = db_session.get(Job, created.created_ids[0])
    job.match_score = 88
    job.match_part_time_fit = True
    db_session.flush()

    ingest_jobs(db_session, "upwork", [_nj("u1", title="New")])
    db_session.refresh(job)

    assert job.title == "New"  # posting fields refresh
    assert job.match_score == 88  # AI score survives
    assert job.match_part_time_fit is True


def test_ingested_jobs_have_no_card_but_list(client, db_session) -> None:
    summary = ingest_jobs(db_session, "upwork", [_nj("u1"), _nj("u2")])

    # Inbox model: ingestion opens no pipeline card.
    for job_id in summary.affected_ids:
        assert db_session.get(Job, job_id).application is None

    # They still surface in GET /api/jobs, each with a null application.
    listed = client.get("/api/jobs").json()
    by_id = {job["id"]: job for job in listed}
    for job_id in summary.affected_ids:
        assert job_id in by_id
        assert by_id[job_id]["application"] is None
