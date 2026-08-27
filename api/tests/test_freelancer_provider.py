"""Freelancer REST provider — mapping + filter translation + auth, hermetic.

No live network reaches Freelancer: the active-projects endpoint is served by an
``httpx.MockTransport`` swapped in for the provider's HTTP client (and the token
endpoint likewise for the refresh path), with credentials monkeypatched onto
``settings``. Coverage mirrors the issue's DoD: a captured search response maps
onto :class:`NormalizedJob` — the hourly-vs-fixed budget, the skills from
``jobs[]``, the client country via the ``users`` map, and ``submitdate`` — the
search filter is translated (``query`` / ``project_types[]`` / passthrough), and a
``401`` triggers exactly one refresh-and-retry over the ``Freelancer-OAuth-V1``
header. Freelancer reports no engagement, so ``workload`` / ``weekly_hours`` stay
``None``.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.models import FreelancerToken
from app.providers import FreelancerProvider
from app.providers import freelancer as freelancer_provider
from app.services import freelancer_oauth


# --- helpers -----------------------------------------------------------------


def _configure(monkeypatch, client_id="cid", client_secret="csecret") -> None:
    monkeypatch.setattr(settings, "freelancer_client_id", client_id)
    monkeypatch.setattr(settings, "freelancer_client_secret", client_secret)


def _seed_valid_token(db, *, access_token="AT-VALID") -> FreelancerToken:
    """A connected, not-yet-expired token, so get_valid_access_token needs no network."""
    row = FreelancerToken(
        provider="freelancer",
        access_token=access_token,
        refresh_token="RT-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    return row


def _mock_rest(monkeypatch, handler) -> None:
    """Route the provider's httpx client through a mock transport (no real network)."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(freelancer_provider, "_http_client", factory)


def _mock_token_endpoint(monkeypatch, handler) -> None:
    """Route the OAuth service's httpx client (used by refresh) through a mock transport."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(freelancer_oauth, "_http_client", factory)


_SUBMITDATE_HOURLY = 1_755_000_000
_SUBMITDATE_FIXED = 1_756_000_000

_HOURLY_PROJECT = {
    "id": 37000001,
    "owner_id": 101,
    "title": "Weekend React developer",
    "seo_url": "javascript/weekend-react-developer",
    "description": "Evenings & weekends, ~10 hrs/week.",
    "type": "hourly",
    "submitdate": _SUBMITDATE_HOURLY,
    "currency": {"id": 1, "code": "usd", "sign": "$", "name": "US Dollar"},
    "budget": {"minimum": 30.0, "maximum": 50.0, "project_type": "hourly"},
    "jobs": [{"id": 9, "name": "React"}, {"id": 13, "name": "TypeScript"}],
}

_FIXED_PROJECT = {
    "id": 37000002,
    "owner_id": 202,
    "title": "Fixed-price landing page",
    "seo_url": "php/fixed-price-landing-page",
    "description": "",
    "type": "fixed",
    "submitdate": _SUBMITDATE_FIXED,
    "currency": {"code": "EUR", "sign": "€", "name": "Euro"},
    "budget": {"minimum": 250.0, "maximum": 750.0, "project_type": "fixed"},
    "jobs": [{"id": 3, "name": "PHP"}],
}

# The owner (employer) directory the API returns when user details are requested;
# client_country is read from here by owner_id.
_USERS = {
    "101": {"id": 101, "username": "acme", "location": {"country": {"name": "United States"}}},
    "202": {"id": 202, "username": "globex", "location": {"country": {"name": "Germany"}}},
}


def _search_response(*projects, users=None) -> dict:
    """A captured active-projects REST response body."""
    projects = projects or (_HOURLY_PROJECT, _FIXED_PROJECT)
    return {
        "status": "success",
        "result": {
            "projects": list(projects),
            "users": _USERS if users is None else users,
            "total_count": len(projects),
        },
    }


# --- identity -----------------------------------------------------------------


def test_provider_key_and_polling() -> None:
    assert FreelancerProvider.key == "freelancer"
    assert FreelancerProvider.supports_polling is True


# --- field mapping (the DoD's core) ------------------------------------------


def test_fetch_maps_projects_to_normalized_jobs(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url).split("?")[0]
        captured["oauth"] = request.headers.get("freelancer-oauth-v1")
        captured["authorization"] = request.headers.get("authorization")
        captured["params"] = request.url.params
        return httpx.Response(200, json=_search_response())

    _mock_rest(monkeypatch, handler)

    jobs = FreelancerProvider(db_session).fetch({"keywords": "react", "budget_type": "hourly"})
    assert len(jobs) == 2
    hourly, fixed = jobs

    # Hourly posting — every mapped field.
    assert hourly.external_id == "37000001"  # project id, as a string
    assert hourly.url == "https://www.freelancer.com/projects/javascript/weekend-react-developer"
    assert hourly.title == "Weekend React developer"
    assert hourly.description == "Evenings & weekends, ~10 hrs/week."
    assert hourly.budget_type == "hourly"
    assert (hourly.budget_min, hourly.budget_max) == (30.0, 50.0)
    assert hourly.currency == "USD"  # currency.code, upper-cased
    assert hourly.skills == ["React", "TypeScript"]  # jobs[].name
    assert hourly.client_country == "United States"  # owner's country, via users[owner_id]
    assert hourly.posted_at == datetime.fromtimestamp(_SUBMITDATE_HOURLY, tz=timezone.utc)
    # Freelancer reports no engagement — the part-time signals stay unset.
    assert hourly.workload is None
    assert hourly.weekly_hours is None
    # The whole node is kept verbatim for audit / re-parse.
    assert hourly.raw["owner_id"] == 101

    # Fixed-price posting.
    assert fixed.external_id == "37000002"
    assert fixed.budget_type == "fixed"
    assert (fixed.budget_min, fixed.budget_max) == (250.0, 750.0)
    assert fixed.currency == "EUR"
    assert fixed.description == ""  # empty description → the NormalizedJob default
    assert fixed.skills == ["PHP"]
    assert fixed.client_country == "Germany"
    assert fixed.posted_at == datetime.fromtimestamp(_SUBMITDATE_FIXED, tz=timezone.utc)
    assert fixed.workload is None and fixed.weekly_hours is None

    # The request hit the confirmed endpoint, carried the Freelancer OAuth header
    # (not Authorization: Bearer), and asked for the projections the mapping needs.
    assert captured["url"] == "https://www.freelancer.com/api/projects/0.1/projects/active"
    assert captured["oauth"] == "AT-VALID"
    assert captured["authorization"] is None
    params = captured["params"]
    assert params["query"] == "react"
    assert params.get_list("project_types[]") == ["hourly"]
    assert params["full_description"] == "true"
    assert params["job_details"] == "true"
    assert params["user_details"] == "true"
    assert params["user_country_details"] == "true"


def test_fetch_folds_category_into_query(db_session, monkeypatch) -> None:
    """A saved search's ``category`` joins ``keywords`` in the one free-text query."""
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = request.url.params
        return httpx.Response(200, json=_search_response())

    _mock_rest(monkeypatch, handler)

    FreelancerProvider(db_session).fetch({"keywords": "react", "category": "web development"})
    assert captured["params"]["query"] == "react web development"


def test_fetch_translates_budget_type_to_project_types(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = request.url.params
        return httpx.Response(200, json=_search_response())

    _mock_rest(monkeypatch, handler)

    FreelancerProvider(db_session).fetch({"budget_type": "fixed"})
    assert captured["params"].get_list("project_types[]") == ["fixed"]


def test_fetch_passes_through_native_filter_keys(db_session, monkeypatch) -> None:
    """Native Freelancer keys — list params (``…[]``) and known scalars — pass verbatim."""
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = request.url.params
        return httpx.Response(200, json=_search_response())

    _mock_rest(monkeypatch, handler)

    FreelancerProvider(db_session).fetch(
        {"min_avg_price": 20, "jobs[]": [9, 13], "project_types[]": ["hourly", "fixed"]}
    )
    params = captured["params"]
    assert params["min_avg_price"] == "20"
    assert params.get_list("jobs[]") == ["9", "13"]
    assert params.get_list("project_types[]") == ["hourly", "fixed"]


def test_fetch_empty_results_returns_no_jobs(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)
    _mock_rest(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"status": "success", "result": {"projects": [], "total_count": 0}}
        ),
    )
    assert FreelancerProvider(db_session).fetch() == []


# --- 401: refresh and retry once ---------------------------------------------


def test_fetch_refreshes_and_retries_once_on_401(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session, access_token="AT-STALE")

    calls = {"rest": 0}

    def rest_handler(request: httpx.Request) -> httpx.Response:
        calls["rest"] += 1
        if calls["rest"] == 1:
            assert request.headers["freelancer-oauth-v1"] == "AT-STALE"
            return httpx.Response(401, json={"status": "error"})
        # Second attempt carries the refreshed token.
        assert request.headers["freelancer-oauth-v1"] == "AT-FRESH"
        return httpx.Response(200, json=_search_response())

    _mock_rest(monkeypatch, rest_handler)
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "AT-FRESH", "expires_in": 3600}),
    )

    jobs = FreelancerProvider(db_session).fetch()
    assert calls["rest"] == 2  # original + exactly one retry
    assert len(jobs) == 2
    # The refreshed token was persisted for the next poll.
    assert freelancer_oauth.get_token(db_session).access_token == "AT-FRESH"


def test_fetch_gives_up_after_one_retry_on_persistent_401(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_valid_token(db_session)

    calls = {"rest": 0}

    def rest_handler(request: httpx.Request) -> httpx.Response:
        calls["rest"] += 1
        return httpx.Response(401, json={"status": "error"})

    _mock_rest(monkeypatch, rest_handler)
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "AT-FRESH2", "expires_in": 3600}),
    )

    with pytest.raises(freelancer_oauth.FreelancerServiceError):
        FreelancerProvider(db_session).fetch()
    assert calls["rest"] == 2  # tried once, refreshed, retried once, then gave up


# --- auth gate: not connected -------------------------------------------------


def test_fetch_when_not_connected_raises_without_hitting_rest(db_session, monkeypatch) -> None:
    _configure(monkeypatch)

    def rest_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("REST must not be called when Freelancer is not connected")

    _mock_rest(monkeypatch, rest_handler)

    with pytest.raises(freelancer_oauth.FreelancerServiceError):
        FreelancerProvider(db_session).fetch()


# --- mapping unit (no DB / no network) ---------------------------------------


def test_normalize_falls_back_to_id_for_url_when_no_seo_url() -> None:
    job = FreelancerProvider._normalize({"id": 555, "title": "x"})
    assert job.external_id == "555"
    assert job.url == "https://www.freelancer.com/projects/555"


def test_normalize_unknown_type_defaults_to_fixed_without_numbers() -> None:
    job = FreelancerProvider._normalize({"id": 1, "seo_url": "a/b", "title": "x"})
    assert job.budget_type == "fixed"
    assert job.budget_min is None and job.budget_max is None
    assert job.workload is None and job.weekly_hours is None


def test_normalize_client_country_falls_back_to_project_location() -> None:
    # No matching owner in the users map → the project's own location country is used.
    job = FreelancerProvider._normalize(
        {"id": 1, "title": "x", "owner_id": 999, "location": {"country": {"name": "Canada"}}},
        {},
    )
    assert job.client_country == "Canada"
