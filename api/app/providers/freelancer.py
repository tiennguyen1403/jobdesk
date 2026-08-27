"""Freelancer.com REST project-search provider — maps postings into :class:`NormalizedJob`.

The polled source: once the OAuth2 flow (#75) has stored a token, this provider
searches Freelancer's *active* projects over httpx and maps every result onto the
app's shared shape, so a Freelancer posting flows through the same ingest /
pipeline / CV / AI path as a manual, captured, or Upwork one. The mapping lives
here and nowhere else — the rest of the app stays source-agnostic.

Auth: the access token comes from :mod:`app.services.freelancer_oauth`
(``get_valid_access_token`` refreshes a clock-expired token first). Freelancer's
REST API authenticates with a *provider-specific* header — ``Freelancer-OAuth-V1:
<token>`` — **not** ``Authorization: Bearer`` (confirmed against the official SDK's
session module). If Freelancer still answers ``401`` — a token revoked or rotated
server-side despite our clock saying it is valid — this forces one ``refresh`` and
retries exactly once; a second ``401`` is a real auth failure and surfaces as
``FreelancerServiceError``.

Read-only: Freelancer's API *can* place bids and send messages, but JobDesk never
calls any mutation — this issues a single GET and nothing else.

Schema confirmed against the official ``freelancer/freelancer-sdk-python`` SDK and
the live REST API (Aug 2026) — field names are NOT assumed:

* base URL: ``https://www.freelancer.com/api`` (SDK ``Session``)
* endpoint: ``GET /projects/0.1/projects/active`` (SDK
  ``search_projects(active_only=True)`` → ``projects/active``)
* query params → the request:
  ``query`` (free-text search), ``project_types[]`` (``fixed`` | ``hourly``),
  ``limit`` / ``offset`` (pagination), and the projection flags that ask the API
  to include otherwise-omitted fields: ``full_description`` (→ ``description``),
  ``job_details`` (→ ``jobs``), ``user_details`` + ``user_country_details``
  (→ the ``users`` map with the owner's country). Flag names come from the SDK's
  ``create_get_projects_project_details_object`` / ``…_user_details_object``.
* response envelope: ``{"status", "result": {"projects": [...], "users": {id:
  user}, "total_count"}}`` (SDK test fixtures). A ``status == "error"`` body is a
  service error.
* project node fields used → ``NormalizedJob``:
  ``id`` → ``external_id``; ``seo_url`` (else ``id``) → the job ``url``; ``title``;
  ``description``; ``type`` (``fixed`` | ``hourly``) → ``budget_type``;
  ``budget.minimum`` / ``budget.maximum`` → ``budget_min`` / ``budget_max``;
  ``currency.code`` → ``currency``; ``jobs[].name`` → ``skills``; the owner's
  ``location.country.name`` (via ``users[owner_id]``, with the project's own
  ``location.country.name`` as a fallback) → ``client_country``; ``submitdate``
  (Unix seconds) → ``posted_at``. The whole node is kept in ``raw``.

Part-time scope: Freelancer exposes no engagement / weekly-hours signal, so
``workload`` and ``weekly_hours`` are deliberately left ``None``. The ingest
guardrail (``services.poller._within_scope``) still HARD-drops anything full-time
and honors ``max_weekly_hours`` — a Freelancer posting simply reports neither, so
it passes the cap and is judged on the rest of the pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from .base import JobProvider, NormalizedJob

if TYPE_CHECKING:  # only for type hints — importing at runtime would risk a cycle
    from sqlalchemy.orm import Session

# The REST base and the active-projects search path (SDK Session + search_projects).
REST_BASE = "https://www.freelancer.com/api"
ACTIVE_PROJECTS_PATH = "/projects/0.1/projects/active"

# A project's public URL is built from its seo_url, e.g.
# ``https://www.freelancer.com/projects/seo/website-seo-20230128``.
_PROJECT_URL_BASE = "https://www.freelancer.com/projects"

# Bound the REST call so a hung endpoint can't wedge the poller.
_HTTP_TIMEOUT = 20.0

# A conservative page size — the poll wants a fresh batch, not the whole board.
_DEFAULT_LIMIT = 50

# Freelancer's two engagement kinds; the search filter and the mapping agree on them.
_PROJECT_TYPES = ("hourly", "fixed")

# Native Freelancer filter scalars that pass through verbatim (list params, which
# end in ``[]`` — ``project_types[]`` / ``jobs[]`` / ``countries[]`` — are matched
# by suffix instead, so a caller can extend the query without this provider
# assuming every field name).
_PASSTHROUGH_KEYS = frozenset(
    {"min_avg_price", "max_avg_price", "limit", "offset", "sort_field", "reverse_sort"}
)

# Last-resort title (the API always sends one; this only guards a malformed node
# so the mapping never raises).
_FALLBACK_TITLE = "(untitled Freelancer project)"


class _Unauthorized(RuntimeError):
    """Internal sentinel: the REST call answered 401 (drives the single retry)."""


def _http_client() -> httpx.Client:
    """The httpx client used for the REST call.

    A seam: tests replace this with a client wired to a mock transport, so the
    suite stays hermetic (no live network to Freelancer).
    """
    return httpx.Client(timeout=_HTTP_TIMEOUT)


def _norm_str(value: object) -> str | None:
    """Trim to a non-empty string, or ``None`` (so a NormalizedJob default applies)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value: object) -> float | None:
    """Coerce a numeric value to ``float``, or ``None`` (absent / blank / malformed)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _budget(project: dict) -> tuple[str, float | None, float | None, str | None]:
    """Derive (budget_type, budget_min, budget_max, currency) from a project node.

    ``type`` (``hourly`` | ``fixed``) drives ``budget_type`` — with ``budget``'s own
    ``project_type`` as a fallback — while ``budget.minimum`` / ``budget.maximum``
    carry the range either way (an hourly rate range or a fixed-price range).
    ``currency.code`` names the currency; anything absent stays ``None`` so the
    NormalizedJob default applies.
    """
    budget = project.get("budget")
    budget = budget if isinstance(budget, dict) else {}
    kind = _norm_str(project.get("type")) or _norm_str(budget.get("project_type"))
    budget_type = "hourly" if (kind is not None and kind.lower() == "hourly") else "fixed"

    budget_min = _num(budget.get("minimum"))
    budget_max = _num(budget.get("maximum"))

    currency = None
    currency_node = project.get("currency")
    if isinstance(currency_node, dict):
        currency = _norm_str(currency_node.get("code"))
        if currency is not None:
            currency = currency.upper()
    return budget_type, budget_min, budget_max, currency


def _skills(value: object) -> list[str]:
    """Map ``jobs`` (``[{id, name}, …]``) → readable skill tags (the job ``name``)."""
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        tag = _norm_str(item.get("name")) if isinstance(item, dict) else _norm_str(item)
        if tag is not None:
            tags.append(tag)
    return tags


def _country_of(entity: object) -> str | None:
    """Dig a country name out of a project/user node, defensively.

    Covers both shapes the API uses depending on the requested projection: a
    ``location.country.name`` (owner ``location`` details) and a ``country`` given
    either as ``{name}`` or as a bare string.
    """
    if not isinstance(entity, dict):
        return None
    location = entity.get("location")
    if isinstance(location, dict):
        country = location.get("country")
        if isinstance(country, dict):
            name = _norm_str(country.get("name"))
            if name is not None:
                return name
        elif country is not None:
            name = _norm_str(country)
            if name is not None:
                return name
    country = entity.get("country")
    if isinstance(country, dict):
        return _norm_str(country.get("name"))
    return _norm_str(country)


def _client_country(project: dict, users: dict) -> str | None:
    """The employer's country — the owner's, via ``users[owner_id]``.

    Prefers the project owner's registered country (the true "client country");
    falls back to the project's own ``location.country.name`` when the owner or its
    country is absent.
    """
    owner_id = project.get("owner_id")
    if owner_id is not None:
        country = _country_of(users.get(str(owner_id)))
        if country is not None:
            return country
    return _country_of(project)


def _project_url(seo_url: str | None, project_id: str | None) -> str:
    """Build the posting's public URL from its seo_url (or the project id as a fallback)."""
    if seo_url is not None:
        return f"{_PROJECT_URL_BASE}/{seo_url.lstrip('/')}"
    if project_id is not None:
        return f"{_PROJECT_URL_BASE}/{project_id}"
    return f"{_PROJECT_URL_BASE}/"


def _posted_at(value: object) -> datetime | None:
    """Map Freelancer's ``submitdate`` (Unix seconds) → an aware UTC datetime, or ``None``."""
    if value is None:
        return None
    try:
        ts = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _project_types(search: dict) -> list[str] | None:
    """Translate an hourly/fixed intent → the ``project_types[]`` filter.

    Reads a friendly ``budget_type`` / ``project_type`` / ``project_types`` key
    (str or list) and keeps only the values Freelancer recognises (``hourly`` /
    ``fixed``); an explicit native ``project_types[]`` key passes through separately.
    """
    raw = (
        search.get("project_types")
        or search.get("project_type")
        or search.get("budget_type")
    )
    if isinstance(raw, str):
        candidates: list = [raw]
    elif isinstance(raw, (list, tuple)):
        candidates = list(raw)
    else:
        return None
    types: list[str] = []
    for candidate in candidates:
        value = _norm_str(candidate)
        if value is not None and value.lower() in _PROJECT_TYPES and value.lower() not in types:
            types.append(value.lower())
    return types or None


class FreelancerProvider(JobProvider):
    """Search Freelancer's active projects via REST and normalize the results.

    Needs the DB session (to read/refresh the stored OAuth token), so like the
    Upwork provider it is constructed per call:
    ``FreelancerProvider(db).fetch(search)``. ``search`` is the app's
    provider-agnostic search shape (``app.schemas.saved_search.SearchQuery``) —
    ``keywords`` / ``category`` become the free-text ``query`` and an hourly/fixed
    intent becomes ``project_types[]``; native Freelancer filter keys (list params
    ending ``[]``, or a known scalar) pass through verbatim so a caller can extend
    the query without this provider assuming every field name.
    """

    key = "freelancer"
    supports_polling = True

    def __init__(self, db: Session) -> None:
        self._db = db

    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        # Lazy import: app.services.freelancer_oauth pulls in the services package,
        # which imports the ingest service, which imports this providers package —
        # importing it at call time (not module load) breaks that cycle.
        from ..services import freelancer_oauth

        body = self._run_search(freelancer_oauth, dict(search or {}))
        result = body.get("result") or {}
        projects = result.get("projects") or []
        users = result.get("users")
        users = users if isinstance(users, dict) else {}
        return [
            self._normalize(project, users)
            for project in projects
            if isinstance(project, dict)
        ]

    # --- search request (auth + one 401 retry) -------------------------------

    def _run_search(self, oauth, search: dict) -> dict:
        params = self._params(search)
        token = oauth.get_valid_access_token(self._db)  # refreshes a clock-expired token
        try:
            return self._get(oauth, token, params)
        except _Unauthorized:
            pass  # token rejected despite a valid clock → refresh once and retry
        token = oauth.refresh(self._db).access_token
        try:
            return self._get(oauth, token, params)
        except _Unauthorized as exc:
            raise oauth.FreelancerServiceError(
                "Freelancer rejected the project search with 401 even after refreshing the token."
            ) from exc

    def _get(self, oauth, token: str, params: dict) -> dict:
        """GET the search and return the parsed body; raise on 401 / transport / bad body."""
        headers = {"Freelancer-OAuth-V1": token, "Accept": "application/json"}
        url = f"{REST_BASE}{ACTIVE_PROJECTS_PATH}"
        try:
            with _http_client() as client:
                resp = client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise oauth.FreelancerServiceError(
                f"Freelancer project search request failed: {type(exc).__name__}"
            ) from exc

        if resp.status_code == 401:
            raise _Unauthorized()
        if resp.status_code != 200:
            raise oauth.FreelancerServiceError(
                f"Freelancer projects endpoint returned HTTP {resp.status_code}."
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise oauth.FreelancerServiceError(
                "Freelancer projects endpoint returned a non-JSON body."
            ) from exc
        if not isinstance(body, dict):
            raise oauth.FreelancerServiceError("Freelancer projects response was not an object.")
        if body.get("status") == "error":
            raise oauth.FreelancerServiceError(
                "Freelancer projects endpoint returned an error status."
            )
        return body

    def _params(self, search: dict) -> dict:
        """Translate the app's search shape into the active-projects query params."""
        # Ask the API to include the otherwise-omitted fields the mapping needs.
        # Booleans are sent as the literal "true" (httpx would render Python True
        # as "True", which Freelancer does not accept).
        params: dict = {
            "full_description": "true",
            "job_details": "true",
            "user_details": "true",
            "user_country_details": "true",
            "limit": _DEFAULT_LIMIT,
            "offset": 0,
        }
        # Fold keywords + category into the one free-text query (mirrors the Upwork
        # provider, so a saved search's ``category`` actually narrows the poll).
        keywords = _norm_str(search.get("keywords")) or _norm_str(search.get("q"))
        category = _norm_str(search.get("category"))
        expression = " ".join(part for part in (keywords, category) if part) or None
        if expression is not None:
            params["query"] = expression

        project_types = _project_types(search)
        if project_types is not None:
            params["project_types[]"] = project_types

        # Explicit passthrough for native Freelancer keys: list params (``…[]``) and
        # a small allowlist of scalars, verbatim (no field-name guessing).
        for name, value in search.items():
            if value is None:
                continue
            if name.endswith("[]") or name in _PASSTHROUGH_KEYS:
                params[name] = value
        return params

    # --- mapping -------------------------------------------------------------

    @staticmethod
    def _normalize(project: dict, users: dict | None = None) -> NormalizedJob:
        users = users if isinstance(users, dict) else {}
        project_id = _norm_str(project.get("id"))
        seo_url = _norm_str(project.get("seo_url"))
        data: dict = {
            "external_id": project_id,
            "url": _project_url(seo_url, project_id),
            "title": _norm_str(project.get("title")) or _FALLBACK_TITLE,
            "raw": dict(project),
        }

        description = _norm_str(project.get("description"))
        if description is not None:
            data["description"] = description

        budget_type, budget_min, budget_max, currency = _budget(project)
        data["budget_type"] = budget_type
        if budget_min is not None:
            data["budget_min"] = budget_min
        if budget_max is not None:
            data["budget_max"] = budget_max
        if currency is not None:
            data["currency"] = currency

        # Freelancer exposes no engagement / weekly-hours — workload & weekly_hours
        # are left None; the ingest guardrail still enforces the part-time scope.

        skills = _skills(project.get("jobs"))
        if skills:
            data["skills"] = skills

        client_country = _client_country(project, users)
        if client_country is not None:
            data["client_country"] = client_country

        posted_at = _posted_at(project.get("submitdate"))
        if posted_at is not None:
            data["posted_at"] = posted_at

        return NormalizedJob(**data)
