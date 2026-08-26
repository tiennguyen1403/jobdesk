"""Upwork OAuth2 endpoints: connect / callback / status / disconnect.

Every route depends on :func:`require_upwork_configured`, so with the client
id/secret unset the whole integration returns a clean **503** (mirroring the AI
layer's missing-key contract) instead of failing deep in the flow. The service
layer (:mod:`app.services.upwork_oauth`) owns the OAuth mechanics and the token
storage; this router is a thin HTTP surface over it and never exposes a token
value — only whether one exists and its expiry.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import UpworkToken
from ..schemas.upwork import UpworkStatus
from ..services import upwork_oauth
from ..services.upwork_oauth import UpworkStateError

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


@router.get(
    "/callback",
    dependencies=[Depends(require_upwork_configured)],
    response_model=UpworkStatus,
)
def callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> UpworkStatus:
    """Handle Upwork's redirect: validate state, exchange the code, store the tokens.

    A denied authorization (Upwork returns ``error``) or a missing/mismatched
    ``code`` / ``state`` is a clean **400**; a failed token exchange surfaces as a
    **502** via the service layer.
    """
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Upwork authorization failed: {error_description or error}",
        )
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' in the Upwork callback.")
    try:
        token = upwork_oauth.exchange_code(db, code=code, state=state)
    except UpworkStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status(token)


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
