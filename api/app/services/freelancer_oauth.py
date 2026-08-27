"""Freelancer.com OAuth2 connect flow + token storage.

The Freelancer provider (#76) needs a valid access token to call Freelancer's
REST API; this module owns obtaining and keeping one. It is a deliberate sibling
of :mod:`app.services.upwork_oauth` — a **separate** token store and service, so
the two connectors never interfere — and mirrors the same graceful-degradation
contract: with no credentials configured it raises :class:`FreelancerConfigError`
*before* any network call (mapped to **503**), and an attempted-but-failed token
call raises :class:`FreelancerServiceError` (mapped to **502**) — never a 500.

Flow (authorization-code grant, RFC 6749):

1. :func:`start_connect` mints a CSRF ``state``, stores it on the single
   :class:`~app.models.FreelancerToken` row, and returns Freelancer's authorize URL.
2. Freelancer redirects back with ``code`` + ``state``; :func:`exchange_code`
   validates the state, swaps the code for tokens at Freelancer's token endpoint,
   and persists them.
3. :func:`refresh` renews an expired access token from the stored refresh token;
   :func:`get_valid_access_token` is the entry point the provider uses.

Secrets: tokens live only in the local DB, are never logged, and are sent
nowhere but Freelancer's token endpoint.

Endpoints verified against the live server (2026-08-27): both the authorize page
and the token endpoint are on ``accounts.freelancer.com`` — the ``www`` host 404s
on ``/oauth/authorize``:

* authorize: ``https://accounts.freelancer.com/oauth/authorize``
* token:     ``https://accounts.freelancer.com/oauth/token``
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import FreelancerToken

# Single-user: exactly one token record, keyed by this provider name.
PROVIDER = "freelancer"

# Both OAuth endpoints live on accounts.freelancer.com — the authorize page AND
# the token exchange. The www host 404s on /oauth/authorize (verified live 2026-08-27).
AUTHORIZE_URL = "https://accounts.freelancer.com/oauth/authorize"
TOKEN_URL = "https://accounts.freelancer.com/oauth/token"

# Treat a token as expired a minute early, so a call never races the boundary.
_EXPIRY_SKEW = timedelta(seconds=60)

# Bound the token HTTP call so a hung endpoint can't wedge a request.
_HTTP_TIMEOUT = 15.0


class FreelancerError(RuntimeError):
    """Base class for Freelancer OAuth failures."""


class FreelancerConfigError(FreelancerError):
    """Freelancer is not configured (client id/secret unset) — maps to 503."""


class FreelancerServiceError(FreelancerError):
    """A token call was attempted but failed, or there is nothing to refresh — maps to 502."""


class FreelancerStateError(FreelancerError):
    """The OAuth callback's ``state`` did not match the pending one (CSRF check) — maps to 400."""


def _require_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) or raise :class:`FreelancerConfigError` (→503)."""
    client_id = settings.freelancer_client_id
    client_secret = settings.freelancer_client_secret
    if not client_id or not client_secret:
        raise FreelancerConfigError(
            "FREELANCER_CLIENT_ID / FREELANCER_CLIENT_SECRET are not set; "
            "the Freelancer integration is disabled."
        )
    return client_id, client_secret


def ensure_configured() -> None:
    """Raise :class:`FreelancerConfigError` (→503) unless Freelancer credentials are set.

    The gate every Freelancer endpoint depends on, so an unconfigured integration
    degrades cleanly (503) rather than failing deep in the flow.
    """
    _require_credentials()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- persistence: the single token row ---------------------------------------


def get_token(db: Session) -> FreelancerToken | None:
    """Return the single stored Freelancer token row, or ``None`` if the flow never ran."""
    return db.scalars(
        select(FreelancerToken).where(FreelancerToken.provider == PROVIDER)
    ).first()


def _get_or_create(db: Session) -> FreelancerToken:
    row = get_token(db)
    if row is None:
        row = FreelancerToken(provider=PROVIDER)
        db.add(row)
    return row


def is_connected(token: FreelancerToken | None) -> bool:
    """Connected ⟺ a row exists *and* holds an access token."""
    return token is not None and bool(token.access_token)


def is_expired(token: FreelancerToken | None, *, skew: timedelta = _EXPIRY_SKEW) -> bool:
    """True if the access token is past (or within ``skew`` of) its expiry.

    An unknown expiry (``expires_at is None``) is treated as *not* expired — there
    is nothing to reason about — so a stored token without a TTL is used as-is.
    """
    if token is None or token.expires_at is None:
        return False
    return token.expires_at <= _now() + skew


# --- Freelancer token endpoint -----------------------------------------------


def _http_client() -> httpx.Client:
    """The httpx client used for token calls.

    A seam: tests replace this with a client wired to a mock transport, so the
    suite stays hermetic (no live network to Freelancer).
    """
    return httpx.Client(timeout=_HTTP_TIMEOUT)


def _token_request(grant: dict) -> dict:
    """POST a grant to Freelancer's token endpoint and return the parsed JSON payload.

    The client credentials are sent in the form body (Freelancer accepts body
    creds). Any transport error, non-200 status, or malformed/incomplete body
    becomes a :class:`FreelancerServiceError` (→502). Neither the request nor the
    response body is logged, so tokens never leak.
    """
    client_id, client_secret = _require_credentials()
    data = {**grant, "client_id": client_id, "client_secret": client_secret}
    try:
        with _http_client() as client:
            resp = client.post(TOKEN_URL, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise FreelancerServiceError(
            f"Freelancer token request failed: {type(exc).__name__}"
        ) from exc

    if resp.status_code != 200:
        # Never echo the body — it may carry sensitive detail. The status is enough.
        raise FreelancerServiceError(
            f"Freelancer token endpoint returned HTTP {resp.status_code}."
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise FreelancerServiceError(
            "Freelancer token endpoint returned a non-JSON body."
        ) from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise FreelancerServiceError(
            "Freelancer token response did not include an access_token."
        )
    return payload


def _store_tokens(db: Session, row: FreelancerToken, payload: dict) -> FreelancerToken:
    """Persist a token payload onto ``row`` and commit.

    Keeps the existing refresh token when the response omits one (a refresh grant
    may not re-issue it), and clears any pending ``auth_state`` now that the
    authorization is complete.
    """
    row.access_token = str(payload["access_token"])
    refresh = payload.get("refresh_token")
    if refresh:
        row.refresh_token = str(refresh)
    scope = payload.get("scope")
    if scope:
        row.scope = str(scope)
    expires_in = payload.get("expires_in")
    if expires_in is None:
        row.expires_at = None
    else:
        try:
            row.expires_at = _now() + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            row.expires_at = None
    row.auth_state = None
    db.commit()
    db.refresh(row)
    return row


# --- public flow --------------------------------------------------------------


def build_authorize_url(
    state: str, *, redirect_uri: str | None = None, scope: str | None = None
) -> str:
    """Construct Freelancer's OAuth2 authorize URL for the authorization-code grant."""
    client_id, _ = _require_credentials()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri or settings.freelancer_redirect_uri,
        "state": state,
    }
    scope = scope if scope is not None else settings.freelancer_scope
    if scope:
        params["scope"] = scope
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def start_connect(db: Session) -> str:
    """Begin the OAuth2 flow: store a fresh CSRF state and return the authorize URL.

    Raises :class:`FreelancerConfigError` (→503) when credentials are unset.
    """
    _require_credentials()
    state = secrets.token_urlsafe(32)
    row = _get_or_create(db)
    row.auth_state = state
    db.commit()
    return build_authorize_url(state)


def exchange_code(
    db: Session, *, code: str, state: str | None, redirect_uri: str | None = None
) -> FreelancerToken:
    """Validate the returned state, exchange the auth code for tokens, and store them.

    Raises :class:`FreelancerConfigError` (→503) if unconfigured,
    :class:`FreelancerStateError` (→400) on a missing/mismatched state, or
    :class:`FreelancerServiceError` (→502) if the token call fails.
    """
    _require_credentials()
    row = get_token(db)
    expected = row.auth_state if row is not None else None
    if not expected or not state or not secrets.compare_digest(state, expected):
        raise FreelancerStateError(
            "Invalid or expired OAuth state; restart the connect flow."
        )

    payload = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or settings.freelancer_redirect_uri,
        }
    )
    return _store_tokens(db, row, payload)


def refresh(db: Session) -> FreelancerToken:
    """Renew the access token from the stored refresh token — the helper #76 relies on.

    Raises :class:`FreelancerConfigError` (→503) if unconfigured, or
    :class:`FreelancerServiceError` (→502) if nothing is stored to refresh or the
    refresh call fails.
    """
    _require_credentials()
    row = get_token(db)
    if row is None or not row.refresh_token:
        raise FreelancerServiceError(
            "No Freelancer refresh token stored; connect the account first."
        )
    payload = _token_request(
        {"grant_type": "refresh_token", "refresh_token": row.refresh_token}
    )
    return _store_tokens(db, row, payload)


def get_valid_access_token(db: Session) -> str:
    """Return a currently-valid access token, refreshing first if it has expired.

    The entry point the Freelancer provider calls. Raises
    :class:`FreelancerConfigError` (→503) if unconfigured and
    :class:`FreelancerServiceError` (→502) if not connected or the refresh fails.
    """
    _require_credentials()
    row = get_token(db)
    if not is_connected(row):
        raise FreelancerServiceError(
            "Freelancer is not connected; run the connect flow first."
        )
    if is_expired(row):
        row = refresh(db)
    assert row is not None and row.access_token is not None  # narrowed by is_connected
    return row.access_token


def disconnect(db: Session) -> None:
    """Forget the stored Freelancer tokens (and any pending state)."""
    row = get_token(db)
    if row is not None:
        db.delete(row)
        db.commit()
