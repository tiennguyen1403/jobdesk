"""Jobs: the ORM round-trip plus the HTTP API (manual provider + CRUD + filters).

``test_job_model_round_trip`` exercises the persistence layer directly. The rest
drive the ``/api/jobs`` endpoints through the ``client`` fixture, which runs each
request inside a transaction that is rolled back afterwards — so a create is
visible to a later request in the same test but never persists. Everything here
honours the app's side-gig scope: only part-time / hourly / project work.
"""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Job


def _job_payload(**overrides) -> dict:
    """A valid part-time job body; override any field for a specific case."""
    payload = {
        "url": "https://example.test/jobs/weekend-react",
        "title": "Weekend React gig",
        "description": "Evenings & weekends only.",
        "budget_type": "hourly",
        "budget_min": 30.0,
        "budget_max": 50.0,
        "workload": "part_time",
        "weekly_hours": 10,
        "duration": "one_to_three_months",
        "skills": ["react", "typescript"],
    }
    payload.update(overrides)
    return payload


def test_job_model_round_trip(db_session) -> None:
    """A job persists and comes back with its Postgres-specific columns intact."""
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


def test_create_opens_saved_application_then_lists(client: TestClient) -> None:
    resp = client.post("/api/jobs", json=_job_payload())
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["id"] > 0
    assert body["source"] == "manual"
    assert body["title"] == "Weekend React gig"
    assert body["skills"] == ["react", "typescript"]
    # POST must open the pipeline card at stage 'saved' (never auto-apply).
    assert body["application"] is not None
    assert body["application"]["status"] == "saved"

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert body["id"] in [job["id"] for job in listed.json()]


def test_workload_filter_narrows_to_part_time(client: TestClient) -> None:
    part = client.post(
        "/api/jobs", json=_job_payload(url="https://example.test/jobs/pt", workload="part_time")
    ).json()
    full = client.post(
        "/api/jobs", json=_job_payload(url="https://example.test/jobs/ft", workload="full_time")
    ).json()

    ids = {job["id"] for job in client.get("/api/jobs", params={"workload": "part_time"}).json()}
    assert part["id"] in ids
    assert full["id"] not in ids


def test_max_weekly_hours_filter(client: TestClient) -> None:
    light = client.post(
        "/api/jobs", json=_job_payload(url="https://example.test/jobs/light", weekly_hours=10)
    ).json()
    heavy = client.post(
        "/api/jobs", json=_job_payload(url="https://example.test/jobs/heavy", weekly_hours=40)
    ).json()

    ids = {job["id"] for job in client.get("/api/jobs", params={"max_weekly_hours": 20}).json()}
    assert light["id"] in ids
    assert heavy["id"] not in ids


def test_budget_type_and_text_filters(client: TestClient) -> None:
    hourly = client.post(
        "/api/jobs",
        json=_job_payload(
            url="https://example.test/jobs/django", title="Django API contractor", budget_type="hourly"
        ),
    ).json()
    fixed = client.post(
        "/api/jobs",
        json=_job_payload(
            url="https://example.test/jobs/logo", title="Logo redesign", budget_type="fixed"
        ),
    ).json()

    by_type = {job["id"] for job in client.get("/api/jobs", params={"budget_type": "fixed"}).json()}
    assert fixed["id"] in by_type
    assert hourly["id"] not in by_type

    by_text = {job["id"] for job in client.get("/api/jobs", params={"q": "django"}).json()}
    assert hourly["id"] in by_text  # case-insensitive match on the title
    assert fixed["id"] not in by_text


def test_get_patch_delete_lifecycle(client: TestClient) -> None:
    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    got = client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["id"] == job_id

    patched = client.patch(f"/api/jobs/{job_id}", json={"title": "Updated title", "weekly_hours": 8})
    assert patched.status_code == 200
    assert patched.json()["title"] == "Updated title"
    assert patched.json()["weekly_hours"] == 8

    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_unknown_job_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/jobs/999999").status_code == 404
    assert client.patch("/api/jobs/999999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/jobs/999999").status_code == 404


def test_invalid_budget_type_is_rejected(client: TestClient) -> None:
    assert client.post("/api/jobs", json=_job_payload(budget_type="salary")).status_code == 422
