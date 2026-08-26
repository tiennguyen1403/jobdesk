"""Browser-capture ingestion — provider mapping + POST /api/capture.

Hermetic: the endpoint tests drive the rolled-back ``client`` fixture (no network
to Upwork), and the provider tests call :class:`CaptureProvider` directly. Coverage
mirrors the issue's DoD: a scraped payload becomes a ``source='capture'`` job with
the original kept in ``raw``; the Upwork job token drives dedupe so re-capturing
the same posting (even with different tracking params) updates in place; and the
required-field contract (url + title) is enforced.
"""
from sqlalchemy import select

from app.models import Job
from app.providers import CaptureProvider

_UPWORK_URL = "https://www.upwork.com/jobs/~021911234567890abcdef"


def _payload(**overrides) -> dict:
    """A realistic scraped Upwork job page payload; override any field."""
    data = {
        "url": f"{_UPWORK_URL}?ref=search#details",  # tracking params + fragment
        "title": "Weekend React developer",
        "description": "Evenings & weekends, ~10 hrs/week.",
        "budget_type": "Hourly",  # scraped wording, normalized by the provider
        "budget_min": 30,
        "budget_max": 50,
        "workload": "Part-time",
        "weekly_hours": 10,
        "skills": ["React", "TypeScript"],
        "captured_at": "2026-08-27T00:00:00Z",  # extra field → preserved in raw
    }
    data.update(overrides)
    return data


def _capture_rows(db) -> list[Job]:
    return list(db.scalars(select(Job).where(Job.source == "capture")))


# --- POST /api/capture -------------------------------------------------------


def test_capture_creates_normalized_job(client, db_session) -> None:
    res = client.post("/api/capture", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()

    assert (body["created"], body["updated"], body["skipped"]) == (1, 0, 0)
    assert body["source"] == "capture"
    assert len(body["job_ids"]) == 1

    job = body["jobs"][0]
    assert job["source"] == "capture"
    # external_id derived from the Upwork token; tracking params/fragment dropped.
    assert job["external_id"] == "~021911234567890abcdef"
    assert job["url"] == _UPWORK_URL
    assert job["title"] == "Weekend React developer"
    assert job["budget_type"] == "hourly"  # "Hourly" -> normalized
    assert job["workload"] == "part_time"  # "Part-time" -> normalized
    assert job["skills"] == ["React", "TypeScript"]
    assert job["application"] is None  # Inbox model: no auto pipeline card

    # The full scrape (incl. the extra key) is kept verbatim in raw.
    row = db_session.get(Job, body["job_ids"][0])
    assert row.raw["captured_at"] == "2026-08-27T00:00:00Z"
    assert row.raw["budget_type"] == "Hourly"  # raw is untouched, not normalized


def test_recapture_dedupes_no_duplicate_row(client, db_session) -> None:
    first = client.post("/api/capture", json=_payload()).json()
    second = client.post("/api/capture", json=_payload(title="Weekend React dev (updated)")).json()

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert second["job_ids"] == first["job_ids"]  # same row, updated in place

    rows = _capture_rows(db_session)
    assert len(rows) == 1
    assert rows[0].title == "Weekend React dev (updated)"


def test_recapture_across_tracking_params_dedupes(client, db_session) -> None:
    # A different URL for the SAME posting (other query params) shares the token,
    # so it dedupes onto one row rather than inserting a second.
    client.post("/api/capture", json=_payload(url=f"{_UPWORK_URL}?ref=a"))
    second = client.post("/api/capture", json=_payload(url=f"{_UPWORK_URL}/?ref=b&x=1")).json()

    assert second["updated"] == 1
    assert len(_capture_rows(db_session)) == 1


def test_capture_lists_in_inbox_without_card(client) -> None:
    body = client.post("/api/capture", json=_payload()).json()
    listed = {job["id"]: job for job in client.get("/api/jobs").json()}

    job_id = body["job_ids"][0]
    assert job_id in listed
    assert listed[job_id]["application"] is None


def test_capture_requires_url_and_title(client) -> None:
    assert client.post("/api/capture", json={"title": "No URL"}).status_code == 422
    assert client.post("/api/capture", json={"url": _UPWORK_URL}).status_code == 422


# --- CaptureProvider (unit) --------------------------------------------------


def test_provider_empty_input_returns_no_jobs() -> None:
    provider = CaptureProvider()
    assert provider.fetch(None) == []
    assert provider.fetch({}) == []
    assert provider.fetch({"url": "   "}) == []  # blank URL is nothing to capture


def test_provider_external_id_prefers_explicit_then_token() -> None:
    provider = CaptureProvider()
    explicit = provider.fetch({"url": _UPWORK_URL, "title": "x", "external_id": "abc"})[0]
    assert explicit.external_id == "abc"

    token = provider.fetch({"url": f"{_UPWORK_URL}?utm=1", "title": "x"})[0]
    assert token.external_id == "~021911234567890abcdef"


def test_provider_external_id_falls_back_to_canonical_url() -> None:
    # A non-Upwork URL with no token dedupes on its canonical form (no query/slash).
    job = CaptureProvider().fetch({"url": "https://Example.com/gig/42/?ref=x#y", "title": "x"})[0]
    assert job.external_id == "https://example.com/gig/42"
    assert job.url == "https://example.com/gig/42"


def test_provider_normalizes_fields_and_keeps_raw() -> None:
    provider = CaptureProvider()
    payload = {
        "url": _UPWORK_URL,
        "title": "  Spaced title  ",
        "budget_type": "Fixed-price",
        "workload": "full time",
        "skills": "Python, FastAPI\nDocker",  # delimited string, not a list
        "currency": "usd",
        "note": "extra",  # unknown key -> raw only
    }
    job = provider.fetch(payload)[0]

    assert job.title == "Spaced title"
    assert job.budget_type == "fixed"
    assert job.workload == "full_time"
    assert job.skills == ["Python", "FastAPI", "Docker"]
    assert job.currency == "USD"
    assert job.raw == payload  # verbatim, including the unknown key


def test_provider_missing_title_uses_fallback() -> None:
    # The endpoint schema requires a title; the provider still never raises.
    job = CaptureProvider().fetch({"url": _UPWORK_URL})[0]
    assert job.title == "(untitled captured job)"
