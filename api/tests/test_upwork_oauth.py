"""Upwork OAuth2 connect flow + token storage — hermetic.

No live network reaches Upwork: the token endpoint is served by an
``httpx.MockTransport`` swapped in for the service's HTTP client, and the
credentials are monkeypatched onto ``settings``. That lets us assert the DoD
directly: the endpoints degrade to a clean 503 when unconfigured; ``/connect``
redirects to Upwork's authorize URL with a CSRF ``state``; ``/callback``
validates the state, exchanges the code with the right grant, and stores the
tokens; the refresh helper renews an expired token; ``/disconnect`` clears it;
and no token value is ever exposed by the API.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from app.config import settings
from app.models import UpworkToken
from app.services import upwork_oauth


# --- helpers -----------------------------------------------------------------


def _configure(monkeypatch, client_id="cid", client_secret="csecret") -> None:
    monkeypatch.setattr(settings, "upwork_client_id", client_id)
    monkeypatch.setattr(settings, "upwork_client_secret", client_secret)


def _unconfigure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "upwork_client_id", None)
    monkeypatch.setattr(settings, "upwork_client_secret", None)


def _mock_token_endpoint(monkeypatch, handler) -> None:
    """Route the service's httpx client through a mock transport (no real network)."""

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(upwork_oauth, "_http_client", factory)


def _token_response(**overrides) -> httpx.Response:
    body = {
        "access_token": "AT-123",
        "refresh_token": "RT-456",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def _begin_flow(client: TestClient) -> str:
    """Hit /connect and return the CSRF state minted into the authorize URL."""
    loc = client.get("/api/upwork/connect", follow_redirects=False).headers["location"]
    return parse_qs(urlparse(loc).query)["state"][0]


# --- 503 gate: unconfigured ---------------------------------------------------


def test_all_endpoints_503_when_unconfigured(client: TestClient, monkeypatch) -> None:
    _unconfigure(monkeypatch)
    cases = [
        ("get", "/api/upwork/connect"),
        ("get", "/api/upwork/callback"),
        ("get", "/api/upwork/status"),
        ("post", "/api/upwork/disconnect"),
    ]
    for method, path in cases:
        resp = getattr(client, method)(path, follow_redirects=False)
        assert resp.status_code == 503, (path, resp.text)
        assert "UPWORK_CLIENT_ID" in resp.json()["detail"]


# --- connect ------------------------------------------------------------------


def test_connect_redirects_to_upwork_authorize_with_state(
    client: TestClient, monkeypatch
) -> None:
    _configure(monkeypatch)
    resp = client.get("/api/upwork/connect", follow_redirects=False)
    assert resp.status_code == 307
    loc = resp.headers["location"]
    assert loc.startswith(
        "https://www.upwork.com/ab/account-security/oauth2/authorize?"
    )
    q = parse_qs(urlparse(loc).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == [settings.upwork_redirect_uri]
    assert q["state"][0]  # present, non-empty
    # A pending flow is not yet "connected".
    assert client.get("/api/upwork/status").json()["connected"] is False


# --- callback: the happy path -------------------------------------------------


def test_callback_exchanges_code_and_stores_tokens(
    client: TestClient, monkeypatch
) -> None:
    _configure(monkeypatch)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return _token_response(scope="")

    _mock_token_endpoint(monkeypatch, handler)

    state = _begin_flow(client)
    resp = client.get(
        "/api/upwork/callback",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )
    # The callback is a browser endpoint: it redirects back into the SPA, not JSON.
    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert location == f"{settings.web_base_url.rstrip('/')}/sources?upwork=connected"
    # Secrets never cross the API boundary — including the redirect target.
    assert "access_token" not in location
    assert "refresh_token" not in location

    # The exchange hit the confirmed token URL with the authorization-code grant.
    assert captured["url"] == "https://www.upwork.com/api/v3/oauth2/token"
    assert "grant_type=authorization_code" in captured["body"]
    assert "code=the-code" in captured["body"]
    assert "redirect_uri=" in captured["body"]
    assert "client_id=cid" in captured["body"]
    assert "client_secret=csecret" in captured["body"]

    # Status agrees, and the tokens persisted.
    assert client.get("/api/upwork/status").json()["connected"] is True


def test_callback_rejects_mismatched_state_without_calling_upwork(
    client: TestClient, monkeypatch
) -> None:
    _configure(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("token endpoint must not be called on a bad state")

    _mock_token_endpoint(monkeypatch, handler)

    _begin_flow(client)  # establishes a state, then we send a different one
    resp = client.get(
        "/api/upwork/callback",
        params={"code": "x", "state": "not-the-real-state"},
        follow_redirects=False,
    )
    # Redirect back to the SPA with an error flag — the token endpoint was never hit.
    assert resp.status_code == 302
    assert (
        resp.headers["location"]
        == f"{settings.web_base_url.rstrip('/')}/sources?upwork=error&reason=state"
    )
    assert client.get("/api/upwork/status").json()["connected"] is False


def test_callback_with_error_param_redirects_to_error(
    client: TestClient, monkeypatch
) -> None:
    _configure(monkeypatch)
    resp = client.get(
        "/api/upwork/callback",
        params={"error": "access_denied", "error_description": "user denied access"},
        follow_redirects=False,
    )
    # A denied grant lands the user back in the app, not on a raw 400 page.
    assert resp.status_code == 302
    assert (
        resp.headers["location"]
        == f"{settings.web_base_url.rstrip('/')}/sources?upwork=error&reason=denied"
    )


def test_callback_upstream_failure_redirects_to_error(
    client: TestClient, monkeypatch
) -> None:
    _configure(monkeypatch)
    _mock_token_endpoint(
        monkeypatch, lambda req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    state = _begin_flow(client)
    resp = client.get(
        "/api/upwork/callback",
        params={"code": "bad", "state": state},
        follow_redirects=False,
    )
    # A failed token exchange redirects to the SPA instead of surfacing a raw 502.
    assert resp.status_code == 302
    assert (
        resp.headers["location"]
        == f"{settings.web_base_url.rstrip('/')}/sources?upwork=error&reason=upstream"
    )
    # A failed exchange leaves the account not connected.
    assert client.get("/api/upwork/status").json()["connected"] is False


# --- disconnect ---------------------------------------------------------------


def test_disconnect_clears_tokens(client: TestClient, monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_token_endpoint(monkeypatch, lambda req: _token_response())
    state = _begin_flow(client)
    client.get(
        "/api/upwork/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert client.get("/api/upwork/status").json()["connected"] is True

    resp = client.post("/api/upwork/disconnect")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
    assert client.get("/api/upwork/status").json()["connected"] is False


# --- refresh helper (called directly, as #4 / #6 will) ------------------------


def _seed_token(db, **overrides) -> UpworkToken:
    fields = {
        "provider": "upwork",
        "access_token": "OLD",
        "refresh_token": "RT-1",
        "expires_at": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    fields.update(overrides)
    row = UpworkToken(**fields)
    db.add(row)
    db.commit()
    return row


def test_refresh_renews_access_token_from_refresh_token(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    _seed_token(db_session)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return _token_response(access_token="NEW", refresh_token="RT-2", expires_in=7200)

    _mock_token_endpoint(monkeypatch, handler)

    updated = upwork_oauth.refresh(db_session)
    assert updated.access_token == "NEW"
    assert updated.refresh_token == "RT-2"
    assert not upwork_oauth.is_expired(updated)
    assert "grant_type=refresh_token" in captured["body"]
    assert "refresh_token=RT-1" in captured["body"]


def test_refresh_keeps_old_refresh_token_when_response_omits_it(
    db_session, monkeypatch
) -> None:
    _configure(monkeypatch)
    _seed_token(db_session)
    # A refresh response that re-issues only the access token.
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600}),
    )
    updated = upwork_oauth.refresh(db_session)
    assert updated.access_token == "NEW"
    assert updated.refresh_token == "RT-1"  # preserved


def test_refresh_without_stored_token_is_service_error(db_session, monkeypatch) -> None:
    _configure(monkeypatch)
    # Nothing stored → nothing to refresh.
    try:
        upwork_oauth.refresh(db_session)
    except upwork_oauth.UpworkServiceError:
        pass
    else:  # pragma: no cover - the assert below reports the failure
        raise AssertionError("expected UpworkServiceError when no refresh token is stored")


def test_get_valid_access_token_auto_refreshes_when_expired(
    db_session, monkeypatch
) -> None:
    _configure(monkeypatch)
    _seed_token(db_session, access_token="OLD", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    _mock_token_endpoint(
        monkeypatch,
        lambda req: httpx.Response(200, json={"access_token": "FRESH", "expires_in": 3600}),
    )
    assert upwork_oauth.get_valid_access_token(db_session) == "FRESH"


def test_get_valid_access_token_when_not_connected_is_service_error(
    db_session, monkeypatch
) -> None:
    _configure(monkeypatch)
    try:
        upwork_oauth.get_valid_access_token(db_session)
    except upwork_oauth.UpworkServiceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected UpworkServiceError when not connected")
