"""Upwork GraphQL job-search provider — maps postings into :class:`NormalizedJob`.

The polled source: once the OAuth2 flow (#3) has stored a token, this provider
runs Upwork's ``marketplaceJobPostingsSearch`` query over httpx and maps every
result onto the app's shared shape, so an Upwork posting flows through the same
ingest / pipeline / CV / AI path as a manual or captured one. The mapping lives
here and nowhere else — the rest of the app stays source-agnostic.

Auth: the access token comes from :mod:`app.services.upwork_oauth`
(``get_valid_access_token`` refreshes a clock-expired token first). If Upwork
still answers ``401`` — a token revoked or rotated server-side despite our clock
saying it is valid — this forces one ``refresh`` and retries exactly once; a
second ``401`` is a real auth failure and surfaces as ``UpworkServiceError``.

Schema confirmed against Upwork's live GraphQL API (Aug 2026) — field names are
NOT assumed:

* endpoint: ``https://api.upwork.com/graphql``
* query:    ``marketplaceJobPostingsSearch(marketPlaceJobFilter, searchType,
  sortAttributes)`` → ``MarketplaceJobPostingSearchConnection`` (``edges.node``
  is a ``MarketplaceJobPostingSearchResult``); ``searchType`` is always
  ``USER_JOBS_SEARCH`` for a user-initiated search.
* node fields used → ``NormalizedJob``:
  ``ciphertext`` → ``external_id`` + the job ``url`` (the stable ``~0…`` id, same
  dedupe key the capture provider uses); ``title``; ``description``;
  ``engagement`` (e.g. "Less than 30 hrs/week" / "30+ hrs/week") →
  ``workload`` + ``weekly_hours``; ``durationLabel`` / ``duration`` →
  ``duration``; ``hourlyBudgetMin`` / ``hourlyBudgetMax`` (``Money``) or
  ``amount`` (``Money``) → ``budget_type`` + ``budget_min`` / ``budget_max`` +
  ``currency``; ``skills{name prettyName}`` → ``skills``;
  ``client.location.country`` → ``client_country``; ``publishedDateTime`` /
  ``createdDateTime`` → ``posted_at``. The whole node is kept in ``raw``.

Part-time scope only, and JobDesk never auto-applies — this reads jobs, nothing
more.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from .base import JobProvider, NormalizedJob

if TYPE_CHECKING:  # only for type hints — importing at runtime would risk a cycle
    from sqlalchemy.orm import Session

GRAPHQL_URL = "https://api.upwork.com/graphql"

# A job's public URL is built from its ciphertext, matching the capture provider
# (docs/capture-bookmarklet.md) so the two sources agree on the canonical URL.
_JOB_URL_TEMPLATE = "https://www.upwork.com/jobs/{key}"

# Bound the GraphQL call so a hung endpoint can't wedge the poller.
_HTTP_TIMEOUT = 20.0

# Upwork reports the weekly commitment in coarse buckets ("Less than 30 hrs/week"
# / "30+ hrs/week"); 30 is the threshold either way, so weekly_hours is the number
# parsed from that string and workload carries the part/full distinction.
_PART_TIME_HOURS = 30

# App workload → Upwork EngagementType (the ``workload_eq`` search filter).
_ENGAGEMENT_BY_WORKLOAD = {"part_time": "PART_TIME", "full_time": "FULL_TIME"}

# Last-resort title (the API always sends one; this only guards a malformed node
# so the mapping never raises).
_FALLBACK_TITLE = "(untitled Upwork job)"

# The exact selection set — only fields confirmed on MarketplaceJobPostingSearchResult.
JOB_SEARCH_QUERY = """
query MarketplaceJobPostingsSearch(
  $marketPlaceJobFilter: MarketplaceJobPostingsSearchFilter,
  $searchType: MarketplaceJobPostingSearchType,
  $sortAttributes: [MarketplaceJobPostingSearchSortAttribute]
) {
  marketplaceJobPostingsSearch(
    marketPlaceJobFilter: $marketPlaceJobFilter,
    searchType: $searchType,
    sortAttributes: $sortAttributes
  ) {
    totalCount
    edges {
      node {
        id
        ciphertext
        title
        description
        engagement
        duration
        durationLabel
        totalApplicants
        createdDateTime
        publishedDateTime
        amount { rawValue currency }
        hourlyBudgetType
        hourlyBudgetMin { rawValue currency }
        hourlyBudgetMax { rawValue currency }
        skills { name prettyName }
        client { location { country } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class _Unauthorized(RuntimeError):
    """Internal sentinel: the GraphQL call answered 401 (drives the single retry)."""


def _http_client() -> httpx.Client:
    """The httpx client used for the GraphQL call.

    A seam: tests replace this with a client wired to a mock transport, so the
    suite stays hermetic (no live network to Upwork).
    """
    return httpx.Client(timeout=_HTTP_TIMEOUT)


def _norm_str(value: object) -> str | None:
    """Trim to a non-empty string, or ``None`` (so a NormalizedJob default applies)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_int(text: str) -> int | None:
    """The first run of digits in ``text`` as an int, or ``None``."""
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def _money(value: object) -> tuple[float | None, str | None]:
    """Map an Upwork ``Money`` ({rawValue, currency}) → (amount, CURRENCY).

    ``rawValue`` is a string (e.g. "30.0"); an absent/blank/malformed value yields
    ``None`` rather than raising.
    """
    if not isinstance(value, dict):
        return None, None
    currency = _norm_str(value.get("currency"))
    if currency is not None:
        currency = currency.upper()
    raw = value.get("rawValue")
    if raw is None or str(raw).strip() == "":
        return None, currency
    try:
        return float(raw), currency
    except (TypeError, ValueError):
        return None, currency


def _budget(node: dict) -> tuple[str, float | None, float | None, str | None]:
    """Derive (budget_type, budget_min, budget_max, currency) from a node.

    Hourly when an hourly budget is present (min/max, or a stated
    ``hourlyBudgetType``); otherwise fixed, with the single ``amount`` kept as the
    ceiling in ``budget_max`` (a fixed price has no lower bound). Falls back to a
    plain ``fixed`` with no numbers when Upwork provided none.
    """
    hourly_min, cur_min = _money(node.get("hourlyBudgetMin"))
    hourly_max, cur_max = _money(node.get("hourlyBudgetMax"))
    budget_kind = _norm_str(node.get("hourlyBudgetType"))
    is_hourly = (
        hourly_min is not None
        or hourly_max is not None
        or (budget_kind is not None and budget_kind.upper() != "NOT_PROVIDED")
    )
    if is_hourly:
        return "hourly", hourly_min, hourly_max, cur_min or cur_max

    amount, currency = _money(node.get("amount"))
    if amount is not None and amount > 0:
        return "fixed", None, amount, currency
    return "fixed", None, None, None


def _workload(engagement: str | None) -> str | None:
    """Map Upwork's engagement wording → 'part_time' | 'full_time' (or ``None``)."""
    if engagement is None:
        return None
    low = engagement.lower()
    if "less than" in low or "as needed" in low:
        return "part_time"
    if "more than" in low or "full" in low or "+" in engagement:
        return "full_time"
    hours = _first_int(engagement)
    if hours is not None:
        return "part_time" if hours < _PART_TIME_HOURS else "full_time"
    return None


def _duration(node: dict) -> str | None:
    """Prefer the human ``durationLabel``; else the ``duration`` enum, lowercased."""
    label = _norm_str(node.get("durationLabel"))
    if label is not None:
        return label
    enum = _norm_str(node.get("duration"))
    return enum.lower() if enum is not None else None


def _skills(value: object) -> list[str]:
    """Map ``[{name, prettyName}, …]`` → readable skill tags (prettyName, else name)."""
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, dict):
            tag = _norm_str(item.get("prettyName")) or _norm_str(item.get("name"))
        else:
            tag = _norm_str(item)
        if tag is not None:
            tags.append(tag)
    return tags


def _client_country(node: dict) -> str | None:
    """Dig ``client.location.country`` out of a node, defensively."""
    client = node.get("client")
    if isinstance(client, dict):
        location = client.get("location")
        if isinstance(location, dict):
            return _norm_str(location.get("country"))
    return None


def _job_url(ciphertext: str | None, node_id: str | None) -> str:
    """Build the posting's public URL from its ciphertext (or id as a fallback)."""
    key = ciphertext or node_id
    if key is not None:
        return _JOB_URL_TEMPLATE.format(key=key)
    return "https://www.upwork.com/jobs/"


class UpworkProvider(JobProvider):
    """Search Upwork via GraphQL and normalize the results.

    Needs the DB session (to read/refresh the stored OAuth token), so unlike the
    stateless manual/capture providers it is constructed per call:
    ``UpworkProvider(db).fetch(search)``. ``search`` is the app's provider-agnostic
    search shape (``app.schemas.saved_search.SearchQuery``) — ``keywords`` and
    ``workload`` are translated to the Upwork filter, and any explicit Upwork
    filter keys (``…_eq`` / ``…_any`` / ``…_all``) pass through verbatim so a
    caller can extend the query without this provider assuming every field name.
    """

    key = "upwork"
    supports_polling = True

    def __init__(self, db: Session) -> None:
        self._db = db

    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        # Lazy import: app.services.upwork_oauth pulls in the services package,
        # which imports the ingest service, which imports this providers package —
        # importing it at call time (not module load) breaks that cycle.
        from ..services import upwork_oauth

        data = self._run_search(upwork_oauth, dict(search or {}))
        connection = ((data.get("data") or {}).get("marketplaceJobPostingsSearch")) or {}
        edges = connection.get("edges") or []
        return [
            self._normalize(edge["node"])
            for edge in edges
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
        ]

    # --- search request (auth + one 401 retry) -------------------------------

    def _run_search(self, oauth, search: dict) -> dict:
        variables = self._variables(search)
        token = oauth.get_valid_access_token(self._db)  # refreshes a clock-expired token
        try:
            return self._post(oauth, token, variables)
        except _Unauthorized:
            pass  # token rejected despite a valid clock → refresh once and retry
        token = oauth.refresh(self._db).access_token
        try:
            return self._post(oauth, token, variables)
        except _Unauthorized as exc:
            raise oauth.UpworkServiceError(
                "Upwork rejected the job search with 401 even after refreshing the token."
            ) from exc

    def _post(self, oauth, token: str, variables: dict) -> dict:
        """POST the query and return the parsed body; raise on 401 / transport / bad body."""
        payload = {"query": JOB_SEARCH_QUERY, "variables": variables}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            with _http_client() as client:
                resp = client.post(GRAPHQL_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise oauth.UpworkServiceError(
                f"Upwork job search request failed: {type(exc).__name__}"
            ) from exc

        if resp.status_code == 401:
            raise _Unauthorized()
        if resp.status_code != 200:
            raise oauth.UpworkServiceError(
                f"Upwork GraphQL endpoint returned HTTP {resp.status_code}."
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise oauth.UpworkServiceError(
                "Upwork GraphQL endpoint returned a non-JSON body."
            ) from exc
        if not isinstance(body, dict):
            raise oauth.UpworkServiceError("Upwork GraphQL response was not an object.")
        errors = body.get("errors")
        if errors:
            if _is_auth_error(errors):
                raise _Unauthorized()  # let the single refresh+retry try to recover
            raise oauth.UpworkServiceError("Upwork GraphQL returned errors for the job search.")
        return body

    @staticmethod
    def _variables(search: dict) -> dict:
        variables: dict = {"searchType": "USER_JOBS_SEARCH"}
        job_filter = UpworkProvider._filter(search)
        if job_filter:
            variables["marketPlaceJobFilter"] = job_filter
        sort = search.get("sortAttributes") or search.get("sort")
        if sort:
            variables["sortAttributes"] = sort
        return variables

    @staticmethod
    def _filter(search: dict) -> dict:
        """Translate the app's search shape into a MarketplaceJobPostingsSearchFilter."""
        job_filter: dict = {}
        # Fold keywords + category into the one verified free-text filter, so a
        # saved search's ``category`` actually narrows the poll instead of being
        # silently dropped (a proper category taxonomy filter can come later).
        keywords = _norm_str(search.get("keywords")) or _norm_str(search.get("q"))
        category = _norm_str(search.get("category"))
        expression = " ".join(part for part in (keywords, category) if part) or None
        if expression is not None:
            job_filter["searchExpression_eq"] = expression
        workload = _norm_str(search.get("workload"))
        engagement = _ENGAGEMENT_BY_WORKLOAD.get(workload) if workload else None
        if engagement is not None:
            job_filter["workload_eq"] = engagement
        # Explicit Upwork filter keys pass through verbatim (no field-name guessing).
        for name, value in search.items():
            if value is not None and name.endswith(("_eq", "_any", "_all")):
                job_filter[name] = value
        return job_filter

    # --- mapping -------------------------------------------------------------

    @staticmethod
    def _normalize(node: dict) -> NormalizedJob:
        ciphertext = _norm_str(node.get("ciphertext"))
        node_id = _norm_str(node.get("id"))
        data: dict = {
            "external_id": ciphertext or node_id,
            "url": _job_url(ciphertext, node_id),
            "title": _norm_str(node.get("title")) or _FALLBACK_TITLE,
            "raw": dict(node),
        }

        description = _norm_str(node.get("description"))
        if description is not None:
            data["description"] = description

        budget_type, budget_min, budget_max, currency = _budget(node)
        data["budget_type"] = budget_type
        if budget_min is not None:
            data["budget_min"] = budget_min
        if budget_max is not None:
            data["budget_max"] = budget_max
        if currency is not None:
            data["currency"] = currency

        engagement = _norm_str(node.get("engagement"))
        workload = _workload(engagement)
        if workload is not None:
            data["workload"] = workload
        weekly_hours = _first_int(engagement) if engagement is not None else None
        if weekly_hours is not None:
            data["weekly_hours"] = weekly_hours

        duration = _duration(node)
        if duration is not None:
            data["duration"] = duration

        skills = _skills(node.get("skills"))
        if skills:
            data["skills"] = skills

        client_country = _client_country(node)
        if client_country is not None:
            data["client_country"] = client_country

        # NormalizedJob parses the ISO string into a datetime.
        posted_at = _norm_str(node.get("publishedDateTime")) or _norm_str(
            node.get("createdDateTime")
        )
        if posted_at is not None:
            data["posted_at"] = posted_at

        return NormalizedJob(**data)


def _is_auth_error(errors: object) -> bool:
    """True if any GraphQL error looks like an auth failure (401-equivalent).

    Some gateways answer 200 with an ``UNAUTHENTICATED`` error instead of a 401;
    treating that as a 401 lets the single refresh+retry recover a rotated token.
    """
    if not isinstance(errors, list):
        return False
    for error in errors:
        if not isinstance(error, dict):
            continue
        code = str(((error.get("extensions") or {}).get("code") or "")).upper()
        if code in {"UNAUTHENTICATED", "UNAUTHORIZED"}:
            return True
        message = str(error.get("message") or "").lower()
        if "unauthenticated" in message or "unauthorized" in message:
            return True
    return False
