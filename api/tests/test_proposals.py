"""Proposals: the ORM round-trip plus the /api/proposals CRUD endpoints.

A proposal is a draft written for one job and editable before the user applies
manually on the platform — pure storage, never auto-submitted. ``job_id`` is
required (there is no base proposal) and deleting a job cascades its proposals
away.

Note on timestamps: the ``client`` fixture runs every request of a test inside
one transaction, and Postgres ``now()`` is the transaction start time, so
``updated_at`` cannot be observed advancing over HTTP here. The round-trip test
asserts the ``onupdate`` is wired instead; the patch test asserts ``created_at``
is preserved.
"""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Job, Proposal


def _make_job(client: TestClient, url: str = "https://example.test/jobs/proposal") -> int:
    """Create a minimal job via the API and return its id (proposals need a job)."""
    resp = client.post("/api/jobs", json={"url": url, "title": "Proposal test job"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_proposal_model_round_trip(db_session) -> None:
    """A proposal persists against its job and its ``updated_at`` is wired to bump."""
    job = Job(source="manual", url="https://example.test/jobs/rt", title="RT job")
    db_session.add(job)
    db_session.flush()  # assign job.id within the transaction

    db_session.add(Proposal(job_id=job.id, content="draft body"))
    db_session.flush()

    proposals = db_session.scalars(select(Proposal).where(Proposal.job_id == job.id)).all()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.id is not None
    assert proposal.content == "draft body"
    assert proposal.created_at is not None
    assert proposal.updated_at is not None
    # DoD "editing content updates updated_at": the column carries an onupdate so
    # any UPDATE refreshes it. (The advance itself can't be seen within one
    # transaction — Postgres now() is fixed for its duration.)
    assert Proposal.__table__.c.updated_at.onupdate is not None


def test_create_get_and_list_by_job(client: TestClient) -> None:
    job_id = _make_job(client)

    resp = client.post("/api/proposals", json={"job_id": job_id, "content": "v1 draft"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] > 0
    assert body["job_id"] == job_id
    assert body["content"] == "v1 draft"
    # Fresh row: the two timestamps start equal.
    assert body["created_at"] == body["updated_at"]

    got = client.get(f"/api/proposals/{body['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]

    listed = client.get("/api/proposals", params={"job_id": job_id})
    assert listed.status_code == 200
    assert body["id"] in [p["id"] for p in listed.json()]


def test_list_by_job_narrows_to_that_job(client: TestClient) -> None:
    job_a = _make_job(client, url="https://example.test/jobs/a")
    job_b = _make_job(client, url="https://example.test/jobs/b")
    a = client.post("/api/proposals", json={"job_id": job_a, "content": "for A"}).json()
    b = client.post("/api/proposals", json={"job_id": job_b, "content": "for B"}).json()

    ids = {p["id"] for p in client.get("/api/proposals", params={"job_id": job_a}).json()}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_content_defaults_to_empty(client: TestClient) -> None:
    job_id = _make_job(client)
    resp = client.post("/api/proposals", json={"job_id": job_id})
    assert resp.status_code == 201, resp.text
    assert resp.json()["content"] == ""


def test_create_requires_an_existing_job(client: TestClient) -> None:
    resp = client.post("/api/proposals", json={"job_id": 999999, "content": "orphan"})
    assert resp.status_code == 404, resp.text


def test_create_requires_job_id(client: TestClient) -> None:
    # job_id is mandatory — there is no base proposal.
    assert client.post("/api/proposals", json={"content": "no job"}).status_code == 422


def test_patch_updates_content_and_preserves_created_at(client: TestClient) -> None:
    job_id = _make_job(client)
    created = client.post("/api/proposals", json={"job_id": job_id, "content": "v1"}).json()

    patched = client.patch(f"/api/proposals/{created['id']}", json={"content": "v2 edited"})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["content"] == "v2 edited"
    # An edit must never rewrite when the row was first created.
    assert body["created_at"] == created["created_at"]


def test_delete_then_missing(client: TestClient) -> None:
    job_id = _make_job(client)
    pid = client.post("/api/proposals", json={"job_id": job_id, "content": "x"}).json()["id"]

    assert client.delete(f"/api/proposals/{pid}").status_code == 204
    assert client.get(f"/api/proposals/{pid}").status_code == 404


def test_unknown_proposal_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/proposals/999999").status_code == 404
    assert client.patch("/api/proposals/999999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/proposals/999999").status_code == 404


def test_deleting_job_cascades_its_proposals(client: TestClient) -> None:
    job_id = _make_job(client)
    pid = client.post("/api/proposals", json={"job_id": job_id, "content": "x"}).json()["id"]

    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    # The proposal dies with its job (ondelete=CASCADE).
    assert client.get(f"/api/proposals/{pid}").status_code == 404
    assert client.get("/api/proposals", params={"job_id": job_id}).json() == []
