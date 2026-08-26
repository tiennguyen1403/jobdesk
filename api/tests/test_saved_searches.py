"""Saved searches: the ORM round-trip plus the /api/saved-searches CRUD endpoints.

A saved search is a reusable, named query the poller (#6) iterates. Part-time
scope is first-class: the ``query`` JSONB carries workload / max-weekly-hours
constraints alongside keywords/category, so polling only pulls
evenings-and-weekends-viable work. JobDesk never auto-applies — a saved search
only finds work.

Note on timestamps: the ``client`` fixture runs every request of a test inside
one transaction, and Postgres ``now()`` is the transaction start time, so
``updated_at`` cannot be observed advancing over HTTP here. The round-trip test
asserts the ``onupdate`` is wired instead; the patch test asserts ``created_at``
is preserved. Tests filter by a unique provider rather than asserting global
counts, so they stay green against a populated dev DB too.
"""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import SavedSearch


def _create(client: TestClient, **overrides) -> dict:
    """POST a saved search (name defaults) and return the created body."""
    payload = {"name": "Evening Python gigs"}
    payload.update(overrides)
    resp = client.post("/api/saved-searches", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_saved_search_model_round_trip(db_session) -> None:
    """A saved search persists, keeps its JSONB query, and wires ``updated_at``."""
    db_session.add(
        SavedSearch(
            name="RT search",
            query={"keywords": "python", "workload": "part_time", "max_weekly_hours": 15},
        )
    )
    db_session.flush()

    rows = db_session.scalars(
        select(SavedSearch).where(SavedSearch.name == "RT search")
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id is not None
    assert row.provider == "upwork"  # column default
    assert row.enabled is True  # column default
    assert row.last_polled_at is None  # never polled
    assert row.query["workload"] == "part_time"
    assert row.query["max_weekly_hours"] == 15
    assert row.created_at is not None
    # DoD "editing bumps updated_at": the column carries an onupdate so any UPDATE
    # refreshes it. (The advance itself can't be seen within one transaction —
    # Postgres now() is fixed for its duration.)
    assert SavedSearch.__table__.c.updated_at.onupdate is not None


def test_create_get_and_list(client: TestClient) -> None:
    created = _create(client, provider="upwork-crud")
    assert created["id"] > 0
    assert created["name"] == "Evening Python gigs"
    assert created["provider"] == "upwork-crud"
    # Fresh row: the two timestamps start equal.
    assert created["created_at"] == created["updated_at"]

    got = client.get(f"/api/saved-searches/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]

    listed = client.get("/api/saved-searches", params={"provider": "upwork-crud"})
    assert listed.status_code == 200
    assert created["id"] in [s["id"] for s in listed.json()]


def test_defaults(client: TestClient) -> None:
    """A bare create fills provider='upwork', enabled=True and a typed query."""
    body = _create(client)
    assert body["provider"] == "upwork"
    assert body["enabled"] is True
    assert body["last_polled_at"] is None
    # The typed query is always present with its part-time keys, defaulted.
    assert body["query"]["keywords"] == ""
    assert body["query"]["workload"] is None
    assert body["query"]["max_weekly_hours"] is None


def test_part_time_constraints_are_stored_and_returned(client: TestClient) -> None:
    """DoD: workload / max weekly hours round-trip through create → get."""
    query = {
        "keywords": "python automation",
        "category": "web-mobile-software-dev",
        "workload": "part_time",
        "max_weekly_hours": 20,
    }
    created = _create(client, name="Part-time only", query=query)
    assert created["query"] == query

    got = client.get(f"/api/saved-searches/{created['id']}").json()
    assert got["query"]["workload"] == "part_time"
    assert got["query"]["max_weekly_hours"] == 20
    assert got["query"]["keywords"] == "python automation"


def test_extra_query_keys_pass_through(client: TestClient) -> None:
    """Provider-specific keys are preserved (query is a flexible JSONB blob)."""
    created = _create(
        client,
        query={"keywords": "react", "client_hires_min": 5, "payment_verified": True},
    )
    got = client.get(f"/api/saved-searches/{created['id']}").json()
    assert got["query"]["client_hires_min"] == 5
    assert got["query"]["payment_verified"] is True


def test_workload_must_be_valid(client: TestClient) -> None:
    """The workload constraint is typed — garbage is rejected, not silently stored."""
    resp = client.post(
        "/api/saved-searches",
        json={"name": "bad", "query": {"workload": "whenever"}},
    )
    assert resp.status_code == 422, resp.text


def test_negative_max_weekly_hours_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/saved-searches",
        json={"name": "bad", "query": {"max_weekly_hours": -5}},
    )
    assert resp.status_code == 422, resp.text


def test_create_requires_name(client: TestClient) -> None:
    assert client.post("/api/saved-searches", json={}).status_code == 422


def test_list_filters_by_provider_and_enabled(client: TestClient) -> None:
    keep = _create(client, provider="freelancer-x", enabled=True)
    other_provider = _create(client, provider="upwork-y", enabled=True)
    disabled = _create(client, provider="freelancer-x", enabled=False)

    # Narrow to one provider.
    ids = {s["id"] for s in client.get(
        "/api/saved-searches", params={"provider": "freelancer-x"}
    ).json()}
    assert keep["id"] in ids
    assert disabled["id"] in ids
    assert other_provider["id"] not in ids

    # Combine provider + enabled: the disabled one drops out.
    enabled_ids = {s["id"] for s in client.get(
        "/api/saved-searches", params={"provider": "freelancer-x", "enabled": True}
    ).json()}
    assert keep["id"] in enabled_ids
    assert disabled["id"] not in enabled_ids


def test_patch_updates_fields_and_preserves_created_at(client: TestClient) -> None:
    created = _create(
        client,
        query={"keywords": "python", "workload": "part_time", "max_weekly_hours": 10},
    )

    patched = client.patch(
        f"/api/saved-searches/{created['id']}",
        json={"enabled": False, "query": {"keywords": "rust", "max_weekly_hours": 8}},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["enabled"] is False
    # query is replaced wholesale, not deep-merged: the old workload key is gone.
    assert body["query"]["keywords"] == "rust"
    assert body["query"]["max_weekly_hours"] == 8
    assert body["query"]["workload"] is None
    # An edit must never rewrite when the row was first created.
    assert body["created_at"] == created["created_at"]


def test_patch_toggle_enabled_only(client: TestClient) -> None:
    """A partial PATCH touches only the keys sent; name is left intact."""
    created = _create(client, name="Keep this name")
    body = client.patch(
        f"/api/saved-searches/{created['id']}", json={"enabled": False}
    ).json()
    assert body["enabled"] is False
    assert body["name"] == "Keep this name"


def test_delete_then_missing(client: TestClient) -> None:
    created = _create(client)
    assert client.delete(f"/api/saved-searches/{created['id']}").status_code == 204
    assert client.get(f"/api/saved-searches/{created['id']}").status_code == 404


def test_unknown_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/saved-searches/999999").status_code == 404
    assert client.patch(
        "/api/saved-searches/999999", json={"enabled": False}
    ).status_code == 404
    assert client.delete("/api/saved-searches/999999").status_code == 404
