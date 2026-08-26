from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .base import JobProvider, NormalizedJob

# Upwork job pages carry a stable ciphertext id in their URL, e.g.
#   https://www.upwork.com/jobs/~021911234567890abcdef
#   https://www.upwork.com/freelance-jobs/apply/Some-Title_~021911234567890abcdef/
# That token is the reliable dedupe key for a captured posting — it survives
# tracking query params, trailing slashes and title slugs.
_UPWORK_JOB_ID = re.compile(r"~0[0-9a-zA-Z]+")

# Last-resort title when a scrape yields none (the payload schema requires one,
# so this only guards a hand-built / malformed payload — the provider never raises).
_FALLBACK_TITLE = "(untitled captured job)"


def _norm_str(value: object) -> str | None:
    """Trim to a non-empty string, or ``None`` (so a default/None can apply)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_url(url: str) -> str:
    """A stable URL key: drop query + fragment, lowercase host, trim trailing '/'.

    Two captures of the same posting that differ only by tracking params or a
    trailing slash collapse to one key, so they dedupe.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


def _external_id(explicit: object, url: str) -> str:
    """Derive the dedupe id: explicit value → Upwork job token → canonical URL.

    Always returns a non-empty id (URL is required), so a captured posting is
    never skipped by the ingestion service the way an id-less manual entry is.
    """
    given = _norm_str(explicit)
    if given:
        return given
    match = _UPWORK_JOB_ID.search(url)
    if match:
        return match.group(0)
    return _canonical_url(url)


def _budget_type(value: object) -> str | None:
    """Normalize scraped budget wording → 'hourly' | 'fixed' (or None if unclear)."""
    text = _norm_str(value)
    if text is None:
        return None
    low = text.lower()
    if "hour" in low:
        return "hourly"
    if "fix" in low or "budget" in low:
        return "fixed"
    return None


def _workload(value: object) -> str | None:
    """Normalize scraped workload wording → 'part_time' | 'full_time' (or None)."""
    text = _norm_str(value)
    if text is None:
        return None
    low = text.lower()
    if "part" in low:
        return "part_time"
    if "full" in low:
        return "full_time"
    return None


def _skills(value: object) -> list[str]:
    """Accept a list or a delimited string; return a clean list of skill tags."""
    if value is None:
        return []
    if isinstance(value, str):
        parts: list[object] = re.split(r"[,\n;]+", value)
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return []
    return [tag for tag in (_norm_str(part) for part in parts) if tag]


class CaptureProvider(JobProvider):
    """Normalize a browser-scraped job payload into the app's shared shape.

    The zero-approval ingestion path: a bookmarklet scrapes the Upwork job page
    the user is viewing and POSTs it to ``/api/capture`` (see
    ``docs/capture-bookmarklet.md``); this provider maps that loosely-structured
    payload onto :class:`NormalizedJob`, so a captured posting behaves exactly
    like one from any other source.

    Scraping is fragile, so mapping is defensive: the full payload is kept
    verbatim in ``raw`` for later re-parsing, ``external_id`` is derived from the
    URL (the reliable dedupe key), and messy/absent fields fall back to the
    NormalizedJob defaults rather than raising.
    """

    key = "capture"
    supports_polling = False

    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        if not search:
            return []
        url = _norm_str(search.get("url"))
        if url is None:
            return []
        return [self._normalize(search, url)]

    @staticmethod
    def _normalize(payload: dict, url: str) -> NormalizedJob:
        # Build only the fields we can trust; everything else falls back to the
        # NormalizedJob defaults. The whole payload is kept verbatim in ``raw``.
        data: dict = {
            "url": _canonical_url(url),
            "external_id": _external_id(payload.get("external_id"), url),
            "title": _norm_str(payload.get("title")) or _FALLBACK_TITLE,
            "raw": dict(payload),
        }

        description = _norm_str(payload.get("description"))
        if description is not None:
            data["description"] = description

        budget_type = _budget_type(payload.get("budget_type"))
        if budget_type is not None:
            data["budget_type"] = budget_type

        for field in ("budget_min", "budget_max"):
            value = payload.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                data[field] = float(value)

        currency = _norm_str(payload.get("currency"))
        if currency is not None:
            data["currency"] = currency.upper()

        workload = _workload(payload.get("workload"))
        if workload is not None:
            data["workload"] = workload

        weekly_hours = payload.get("weekly_hours")
        if isinstance(weekly_hours, int) and not isinstance(weekly_hours, bool):
            data["weekly_hours"] = weekly_hours

        duration = _norm_str(payload.get("duration"))
        if duration is not None:
            data["duration"] = duration

        skills = _skills(payload.get("skills"))
        if skills:
            data["skills"] = skills

        client_country = _norm_str(payload.get("client_country"))
        if client_country is not None:
            data["client_country"] = client_country

        posted_at = payload.get("posted_at")
        if posted_at:
            # NormalizedJob parses an ISO string; the request schema already
            # validated it, so this is a plain assignment.
            data["posted_at"] = posted_at

        return NormalizedJob(**data)
