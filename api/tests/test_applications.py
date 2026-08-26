"""The application pipeline round-trips over the HTTP API.

Every job added through the Jobs API opens a pipeline card, so these tests use
that as the setup path, then exercise the board feed: list + filter by stage,
move a card, and edit its notes — confirming both a move and an edit persist
across a re-fetch (the board's "reload"). They also cover status validation,
404s, and opening a card for a job that arrived without one (future providers).
"""
from app.models import Job


def _create_job(client, **overrides) -> dict:
    """Add a part-time job via the API and return the created JobRead payload."""
    payload = {
        "url": "https://example.test/jobs/weekend-react",
        "title": "Weekend React gig",
        "description": "Evenings & weekends only.",
        "budget_type": "hourly",
        "budget_min": 30.0,
        "budget_max": 50.0,
        "currency": "USD",
        "workload": "part_time",
        "weekly_hours": 10,
        "duration": "one_to_three_months",
        "skills": ["react", "typescript"],
    }
    payload.update(overrides)
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_embeds_job_summary(client) -> None:
    _create_job(client)

    resp = client.get("/api/applications")
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1

    card = cards[0]
    assert card["status"] == "saved"  # a fresh card starts in the first column
    # The board needs the job's headline facts alongside each card.
    job = card["job"]
    assert job["title"] == "Weekend React gig"
    assert job["url"] == "https://example.test/jobs/weekend-react"
    assert job["budget_type"] == "hourly"
    assert job["budget_min"] == 30.0
    assert job["workload"] == "part_time"  # part-time scope carries through
    assert job["weekly_hours"] == 10


def test_filter_by_status(client) -> None:
    _create_job(client)  # opens a card at 'saved'

    assert client.get("/api/applications", params={"status": "saved"}).json() != []
    assert client.get("/api/applications", params={"status": "applied"}).json() == []


def test_move_stage_persists(client) -> None:
    app_id = _create_job(client)["application"]["id"]

    patched = client.patch(f"/api/applications/{app_id}", json={"status": "applied"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "applied"

    # Persists across a reload (a fresh GET).
    assert client.get(f"/api/applications/{app_id}").json()["status"] == "applied"


def test_edit_notes_persists(client) -> None:
    app_id = _create_job(client)["application"]["id"]

    client.patch(f"/api/applications/{app_id}", json={"notes": "Follow up Monday."})
    got = client.get(f"/api/applications/{app_id}").json()
    assert got["notes"] == "Follow up Monday."
    assert got["status"] == "saved"  # a notes edit leaves the stage untouched


def test_invalid_status_rejected(client) -> None:
    app_id = _create_job(client)["application"]["id"]

    resp = client.patch(f"/api/applications/{app_id}", json={"status": "banana"})
    assert resp.status_code == 422


def test_get_missing_returns_404(client) -> None:
    assert client.get("/api/applications/999999").status_code == 404


def test_patch_missing_returns_404(client) -> None:
    resp = client.patch("/api/applications/999999", json={"status": "applied"})
    assert resp.status_code == 404


def test_open_card_for_untracked_job(client, db_session) -> None:
    # A provider inserts a job without a pipeline card (bypasses the Jobs API).
    job = Job(
        source="capture",
        url="https://example.test/jobs/untracked",
        title="Captured gig",
        workload="part_time",
    )
    db_session.add(job)
    db_session.flush()

    created = client.post(f"/api/jobs/{job.id}/application")
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "saved"
    assert body["job"]["id"] == job.id

    # A second attempt conflicts: the 1–1 card already exists.
    assert client.post(f"/api/jobs/{job.id}/application").status_code == 409


def test_open_card_for_missing_job_returns_404(client) -> None:
    assert client.post("/api/jobs/999999/application").status_code == 404
