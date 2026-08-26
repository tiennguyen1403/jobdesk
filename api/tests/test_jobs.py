"""A job round-trips through the DB: create a posting, then find it in a listing.

This exercises the persistence layer directly because the Jobs HTTP API (create
+ list) is a separate issue (#20) and does not exist yet. Once it lands, an
API-level ``create -> list`` test can build on the ``client`` fixture the same
way ``test_health`` does. The fixture keeps only part-time / hourly / project
work, honouring the app's side-gig scope.
"""
from sqlalchemy import select

from app.models import Job


def test_create_then_list_job(db_session) -> None:
    url = "https://example.test/jobs/harness-smoke"
    db_session.add(
        Job(
            source="manual",
            url=url,
            title="Weekend React gig",
            description="Evenings & weekends only.",
            budget_type="hourly",
            budget_min=30.0,
            budget_max=50.0,
            workload="part_time",
            weekly_hours=10,
            duration="one_to_three_months",
            skills=["react", "typescript"],
            raw={"note": "test fixture"},
        )
    )
    db_session.flush()  # INSERT within the transaction and populate the PK

    jobs = db_session.scalars(select(Job).where(Job.url == url)).all()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id is not None
    assert job.source == "manual"
    assert job.title == "Weekend React gig"
    assert job.budget_type == "hourly"
    assert job.workload == "part_time"
    assert job.weekly_hours == 10
    # Postgres-specific columns round-trip: ARRAY(String) and JSONB.
    assert job.skills == ["react", "typescript"]
    assert job.raw == {"note": "test fixture"}
