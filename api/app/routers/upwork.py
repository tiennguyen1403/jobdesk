"""Upwork OAuth2 endpoints: connect / callback / status / disconnect.

Every route depends on :func:`require_upwork_configured`, so with the client
id/secret unset the whole integration returns a clean **503** (mirroring the AI
layer's missing-key contract) instead of failing deep in the flow. The service
layer (:mod:`app.services.upwork_oauth`) owns the OAuth mechanics and the token
storage; this router is a thin HTTP surface over it and never exposes a token
value — only whether one exists and its expiry.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import UpworkToken
from ..schemas.upwork import UpworkStatus
from ..services import upwork_oauth
from ..services.upwork_oauth import UpworkServiceError, UpworkStateError

router = APIRouter(prefix="/upwork", tags=["upwork"])


def require_upwork_configured() -> None:
    """Gate: raise :class:`UpworkConfigError` (→503) unless credentials are set."""
    upwork_oauth.ensure_configured()


def _status(token: UpworkToken | None) -> UpworkStatus:
    return UpworkStatus(
        provider=upwork_oauth.PROVIDER,
        connected=upwork_oauth.is_connected(token),
        expired=upwork_oauth.is_expired(token),
        expires_at=token.expires_at if token is not None else None,
        scope=token.scope if token is not None else None,
    )


@router.get("/connect", dependencies=[Depends(require_upwork_configured)])
def connect(db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect the user to Upwork's OAuth2 authorize page to grant access.

    Stores a fresh CSRF ``state`` first, then 307-redirects to the authorize URL.
    """
    url = upwork_oauth.start_connect(db)
    return RedirectResponse(url, status_code=307)


def _sources_redirect(outcome: str, *, reason: str | None = None) -> RedirectResponse:
    """302-redirect back to the SPA's ``/sources``, tagged with the OAuth outcome.

    302 (Found), not 307: this is an ordinary "now GET this page" navigation — both
    hops are GETs, so 307's method-preservation buys nothing, and 302 is the
    idiomatic post-OAuth landing redirect. No token value ever rides in the URL.
    """
    params = {"upwork": outcome}
    if reason:
        params["reason"] = reason
    url = f"{settings.web_base_url.rstrip('/')}/sources?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.get("/callback", dependencies=[Depends(require_upwork_configured)])
def callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Upwork's browser redirect, then land the user back in the SPA.

    Upwork navigates the user's tab here, so *every* outcome is a redirect to
    ``/sources`` — the user never sees raw JSON or a 4xx/5xx page:

    * success → ``?upwork=connected``
    * denied grant, missing/mismatched ``code``/``state``, or a failed token
      exchange → ``?upwork=error&reason=<short>``

    The token-exchange mechanics live in :mod:`app.services.upwork_oauth` and are
    unchanged. An *unconfigured* integration is still a clean **503** from
    :func:`require_upwork_configured`, which runs before this body.
    """
    if error:
        return _sources_redirect("error", reason="denied")
    if not code:
        return _sources_redirect("error", reason="missing_code")
    try:
        upwork_oauth.exchange_code(db, code=code, state=state)
    except UpworkStateError:
        return _sources_redirect("error", reason="state")
    except UpworkServiceError:
        return _sources_redirect("error", reason="upstream")
    return _sources_redirect("connected")


@router.get(
    "/status",
    dependencies=[Depends(require_upwork_configured)],
    response_model=UpworkStatus,
)
def status(db: Session = Depends(get_db)) -> UpworkStatus:
    """Report whether the Upwork account is connected and when the token expires."""
    return _status(upwork_oauth.get_token(db))


@router.post(
    "/disconnect",
    dependencies=[Depends(require_upwork_configured)],
    response_model=UpworkStatus,
)
def disconnect(db: Session = Depends(get_db)) -> UpworkStatus:
    """Clear the stored Upwork tokens; the account is disconnected afterward."""
    upwork_oauth.disconnect(db)
    return _status(None)
