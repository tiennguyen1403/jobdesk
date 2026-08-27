"""Upwork GraphQL provider — mapping + auth, hermetic.

No live network reaches Upwork: the GraphQL endpoint is served by an
``httpx.MockTransport`` swapped in for the provider's HTTP client (and the token
endpoint likewise for the refresh path), with credentials monkeypatched onto
``settings``. Coverage mirrors the issue's DoD: a captured search response maps
onto :class:`NormalizedJob` — especially the part-time signals
(``workload`` / ``weekly_hours`` / ``duration``) and the hourly-vs-fixed budget —
and a ``401`` triggers exactly one refresh-and-retry.
"""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.models import UpworkToken
from app.providers import UpworkProvider
from app.providers import upwork as upwork_provider
from app.services import upwork_oauth


# --- helpers -----------------------------------------------------------------


def _configure(monkeypatch, client_id="cid", client_secret="csecret") -> None:
    monkeypatch.setattr(settings, "upwork_client_id", client_id)
    monkeypatch.setattr(settings, "upwork_client_secret", client_secret)


def _seed_valid_token(db, *, access_token="AT-VALID") -> UpworkToken:
    """A connected, not-yet-expired token, so get_valid_access_token needs no network."""
    row = UpworkToken(
        provider="upwork",
        access_token=access_token,
        refresh_token="RT-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    return row


def _mock_graphql(monkeypatch, handler) -> None:
    """Route the provider's httpx client through a mock transport (no real network)."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(upwork_provider, "_http_client", factory)


def _mock_token_endpoint(monkeypatch, handler) -> None:
    """Route the OAuth service's httpx client (used by refresh) through a mock transport."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(upwork_oauth, "_http_client", factory)


_HOURLY_NODE = {
    "id": "1234567890",
    "ciphertext": "~021911234567890abcdef",
    "title": "Weekend React developer",
    "description": "Evenings & weekends, ~10 hrs/week.",
    "engagement": "Less than 30 hrs/week",
    "duration": "MONTH",
    "durationLabel": "1 to 3 months",
    "totalApplicants": 5,
    "createdDateTime": "2026-08-20T10:00:00Z",
    "publishedDateTime": "2026-08-21T12:30:00Z",
    "amount": None,
    "hourlyBudgetType": "MANUAL",
    "hourlyBudgetMin": {"rawValue": "30.0", "currency": "USD"},
    "hourlyBudgetMax": {"rawValue": "50.0", "currency": "USD"},
    "skills": [
        {"name": "react", "prettyName": "React"},
        {"name": "typescript", "prettyName": "TypeScript"},
    ],
    "client": {"location": {"country": "United States"}},
}

_FIXED_NODE = {
    "id": "9998887776",
    "ciphertext": "~019abcdef0123456789",
    "title": "Fixed-price landing page",
    "description": "",
    "engagement": "30+ hrs/week",
    "duration": "ONGOING",
    "durationLabel": None,
    "createdDateTime": "2026-08-25T09:00:00Z",
    "publishedDateTime": None,
    "amount": {"rawValue": "1500", "currency": "USD"},
    "hourlyBudgetType": "NOT_PROVIDED",
    "hourlyBudgetMin": None,
    "hourlyBudgetMax": None,
    "skills": [{"name": "python", "prettyName": "Python"}],
    "client": {"location": {"country": "Germany"}},
}


def _search_response(*nodes) -> dict:
    """A captured ``marketplaceJobPostingsSearch`` GraphQL response body."""
    nodes = nodes or (_HOURLY_NODE, _FIXED_NODE)
    return {
        "data": {
            "marketplaceJobPostingsSearch": {
                "totalCount": len(nodes),
                "edges": [{"node": node} for node in nodes],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }


# --- identity -----------------------------------------------------------------


def test_provider_key_and_polling() -> None:
    assert UpworkProvider.key == "upwork"
    assert UpworkProvider.supports_polling is True


# --- field mapping (the DoD's core) ------------------------------------------


def test_fetch_maps_search_results_to_normalized_jobs(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_search_response())

    _mock_graphql(monkeypatch, handler)

    jobs = UpworkProvider(db_session).fetch({"keywords": "react", "workload": "part_time"})
    assert len(jobs) == 2
    hourly, fixed = jobs

    # Hourly, part-time posting — every mapped field.
    assert hourly.external_id == "~021911234567890abcdef"  # ciphertext, not the numeric id
    assert hourly.url == "https://www.upwork.com/jobs/~021911234567890abcdef"
    assert hourly.title == "Weekend React developer"
    assert hourly.description == "Evenings & weekends, ~10 hrs/week."
    assert hourly.budget_type == "hourly"
    assert (hourly.budget_min, hourly.budget_max) == (30.0, 50.0)
    assert hourly.currency == "USD"
    # Part-time signals — the fields the scope depends on.
    assert hourly.workload == "part_time"
    assert hourly.weekly_hours == 30
    assert hourly.duration == "1 to 3 months"
    assert hourly.skills == ["React", "TypeScript"]  # prettyName preferred
    assert hourly.client_country == "United States"
    assert hourly.posted_at is not None
    assert (hourly.posted_at.year, hourly.posted_at.month, hourly.posted_at.day) == (
        2026,
        8,
        21,
    )  # publishedDateTime wins over createdDateTime
    # The whole node is kept verbatim for audit / re-parse.
    assert hourly.raw["totalApplicants"] == 5

    # Fixed-price, full-time posting.
    assert fixed.external_id == "~019abcdef0123456789"
    assert fixed.budget_type == "fixed"
    assert fixed.budget_min is None
    assert fixed.budget_max == 1500.0  # the single amount, kept as the ceiling
    assert fixed.currency == "USD"
    assert fixed.workload == "full_time"
    assert fixed.weekly_hours == 30
    assert fixed.duration == "ongoing"  # durationLabel absent → duration enum, lowercased
    assert fixed.posted_at is not None
    assert fixed.posted_at.day == 25  # falls back to createdDateTime

    # The request hit the confirmed endpoint, bearer the stored token, and carried
    # the translated filter + the user-jobs search type.
    assert captured["url"] == "https://api.upwork.com/graphql"
    assert captured["auth"] == "Bearer AT-VALID"
    variables = captured["json"]["variables"]
    assert variables["searchType"] == "USER_JOBS_SEARCH"
    assert variables["marketPlaceJobFilter"]["searchExpression_eq"] == "react"
    assert variables["marketPlaceJobFilter"]["workload_eq"] == "PART_TIME"
    assert "marketplaceJobPostingsSearch" in captured["json"]["query"]


def test_fetch_folds_category_into_search_expression(db_session, monkeypatch) -> None:
    """A saved search's ``category`` is no longer dropped — it joins ``keywords`` in
    the one verified ``searchExpression`` filter, so polling actually uses it."""
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_search_response())

    _mock_graphql(monkeypatch, handler)

    UpworkProvider(db_session).fetch({"keywords": "react", "category": "web development"})

    job_filter = captured["json"]["variables"]["marketPlaceJobFilter"]
    assert job_filter["searchExpression_eq"] == "react web development"


def test_fetch_empty_results_returns_no_jobs(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)
    _mock_graphql(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={"data": {"marketplaceJobPostingsSearch": {"edges": [], "totalCount": 0}}},
        ),
    )
    assert UpworkProvider(db_session).fetch() == []


# --- 401: refresh and retry once ---------------------------------------------


def test_fetch_refreshes_and_retries_once_on_401(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session, access_token="AT-STALE")

    calls = {"graphql": 0}

    def gql_handler(request: httpx.Request) -> httpx.Response:
        calls["graphql"] += 1
        if calls["graphql"] == 1:
            assert request.headers["authorization"] == "Bearer AT-STALE"
            return httpx.Response(401, json={"error": "unauthorized"})
        # Second attempt carries the refreshed token.
        assert request.headers["authorization"] == "Bearer AT-FRESH"
        return httpx.Response(200, json=_search_response())

    _mock_graphql(monkeypatch, gql_handler)
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "AT-FRESH", "expires_in": 3600}),
    )

    jobs = UpworkProvider(db_session).fetch()
    assert calls["graphql"] == 2  # original + exactly one retry
    assert len(jobs) == 2
    # The refreshed token was persisted for the next poll.
    assert upwork_oauth.get_token(db_session).access_token == "AT-FRESH"


def test_fetch_gives_up_after_one_retry_on_persistent_401(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    calls = {"graphql": 0}

    def gql_handler(request: httpx.Request) -> httpx.Response:
        calls["graphql"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    _mock_graphql(monkeypatch, gql_handler)
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "AT-FRESH2", "expires_in": 3600}),
    )

    with pytest.raises(upwork_oauth.UpworkServiceError):
        UpworkProvider(db_session).fetch()
    assert calls["graphql"] == 2  # tried once, refreshed, retried once, then gave up


# --- auth gate: not connected -------------------------------------------------


def test_fetch_when_not_connected_raises_without_hitting_graphql(
    db_session, monkeypatch
) -> None:
    _configure(monkeypatch)

    def gql_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("GraphQL must not be called when Upwork is not connected")

    _mock_graphql(monkeypatch, gql_handler)

    with pytest.raises(upwork_oauth.UpworkServiceError):
        UpworkProvider(db_session).fetch()


# --- mapping unit (no DB / no network) ---------------------------------------


def test_normalize_falls_back_to_id_for_url_when_no_ciphertext() -> None:
    job = UpworkProvider._normalize({"id": "555", "title": "x"})
    assert job.external_id == "555"
    assert job.url == "https://www.upwork.com/jobs/555"


def test_normalize_unknown_budget_defaults_to_fixed_without_numbers() -> None:
    job = UpworkProvider._normalize(
        {"id": "1", "ciphertext": "~02x", "title": "x", "hourlyBudgetType": "NOT_PROVIDED"}
    )
    assert job.budget_type == "fixed"
    assert job.budget_min is None and job.budget_max is None
