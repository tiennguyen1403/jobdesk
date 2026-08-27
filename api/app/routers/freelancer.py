"""Freelancer OAuth2 endpoints: connect / callback / status / disconnect.

A deliberate sibling of :mod:`app.routers.upwork`. Every route depends on
:func:`require_freelancer_configured`, so with the client id/secret unset the
whole integration returns a clean **503** (mirroring the AI layer's missing-key
contract) instead of failing deep in the flow. The service layer
(:mod:`app.services.freelancer_oauth`) owns the OAuth mechanics and the token
storage; this router is a thin HTTP surface over it and never exposes a token
value — only whether one exists and its expiry.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import FreelancerToken
from ..schemas.freelancer import FreelancerStatus
from ..services import freelancer_oauth
from ..services.freelancer_oauth import FreelancerServiceError, FreelancerStateError

router = APIRouter(prefix="/freelancer", tags=["freelancer"])


def require_freelancer_configured() -> None:
    """Gate: raise :class:`FreelancerConfigError` (→503) unless credentials are set."""
    freelancer_oauth.ensure_configured()


def _status(token: FreelancerToken | None) -> FreelancerStatus:
    return FreelancerStatus(
        provider=freelancer_oauth.PROVIDER,
        connected=freelancer_oauth.is_connected(token),
        expired=freelancer_oauth.is_expired(token),
        expires_at=token.expires_at if token is not None else None,
        scope=token.scope if token is not None else None,
    )


@router.get("/connect", dependencies=[Depends(require_freelancer_configured)])
def connect(db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect the user to Freelancer's OAuth2 authorize page to grant access.

    Stores a fresh CSRF ``state`` first, then 307-redirects to the authorize URL.
    """
    url = freelancer_oauth.start_connect(db)
    return RedirectResponse(url, status_code=307)


def _sources_redirect(outcome: str, *, reason: str | None = None) -> RedirectResponse:
    """302-redirect back to the SPA's ``/sources``, tagged with the OAuth outcome.

    302 (Found), not 307: this is an ordinary "now GET this page" navigation — both
    hops are GETs, so 307's method-preservation buys nothing, and 302 is the
    idiomatic post-OAuth landing redirect. No token value ever rides in the URL.
    """
    params = {"freelancer": outcome}
    if reason:
        params["reason"] = reason
    url = f"{settings.web_base_url.rstrip('/')}/sources?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.get("/callback", dependencies=[Depends(require_freelancer_configured)])
def callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Freelancer's browser redirect, then land the user back in the SPA.

    Freelancer navigates the user's tab here, so *every* outcome is a redirect to
    ``/sources`` — the user never sees raw JSON or a 4xx/5xx page:

    * success → ``?freelancer=connected``
    * denied grant, missing/mismatched ``code``/``state``, or a failed token
      exchange → ``?freelancer=error&reason=<short>``

    The token-exchange mechanics live in :mod:`app.services.freelancer_oauth` and
    are unchanged. An *unconfigured* integration is still a clean **503** from
    :func:`require_freelancer_configured`, which runs before this body.
    """
    if error:
        return _sources_redirect("error", reason="denied")
    if not code:
        return _sources_redirect("error", reason="missing_code")
    try:
        freelancer_oauth.exchange_code(db, code=code, state=state)
    except FreelancerStateError:
        return _sources_redirect("error", reason="state")
    except FreelancerServiceError:
        return _sources_redirect("error", reason="upstream")
    return _sources_redirect("connected")


@router.get(
    "/status",
    dependencies=[Depends(require_freelancer_configured)],
    response_model=FreelancerStatus,
)
def status(db: Session = Depends(get_db)) -> FreelancerStatus:
    """Report whether the Freelancer account is connected and when the token expires."""
    return _status(freelancer_oauth.get_token(db))


@router.post(
    "/disconnect",
    dependencies=[Depends(require_freelancer_configured)],
    response_model=FreelancerStatus,
)
def disconnect(db: Session = Depends(get_db)) -> FreelancerStatus:
    """Clear the stored Freelancer tokens; the account is disconnected afterward."""
    freelancer_oauth.disconnect(db)
    return _status(None)
