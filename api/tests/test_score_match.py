"""score_match: structured part-time fit scoring, persistence, and ai_run logging.

Hermetic — the Anthropic client is monkeypatched with a fake, so no network hits
Anthropic. The fake records the request it receives, which lets us assert the DoD
directly: the prompt weighs workload / weekly_hours / duration, the reply is asked
for as structured JSON (not scraped from prose), the score + reasons + part-time
flag persist on the job, and exactly one ``score_match`` ai_run is logged (linked
to the job). The missing-key and upstream-failure paths stay clean (503 / 502) and
leave the job unscored.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import settings


def _job_payload(**overrides) -> dict:
    """A valid part-time job body; override any field for a specific case."""
    payload = {
        "url": "https://example.test/jobs/score",
        "title": "Weekend React gig",
        "description": "Evenings & weekends only.",
        "budget_type": "hourly",
        "budget_min": 30.0,
        "budget_max": 50.0,
        "workload": "part_time",
        "weekly_hours": 10,
        "duration": "one_to_three_months",
        "skills": ["react", "typescript"],
    }
    payload.update(overrides)
    return payload


def _score_json(score: int = 82, reasons=None, part_time_fit: bool = True) -> str:
    """Serialize a well-formed structured score reply, as the API would return."""
    return json.dumps(
        {
            "score": score,
            "reasons": reasons if reasons is not None else ["Part-time workload", "~10h/week"],
            "part_time_fit": part_time_fit,
        }
    )


def _fake_response(text: str, input_tokens: int = 120, output_tokens: int = 40):
    """A minimal stand-in for an anthropic Message: a thinking block then JSON text."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="...", text=""),  # filtered out
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
        model="claude-opus-5",
        stop_reason="end_turn",
    )


def _install_fake_client(monkeypatch, *, create) -> None:
    """Point app.ai.service at a fake Anthropic client whose create() is `create`."""
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            self.messages = SimpleNamespace(create=create)

    monkeypatch.setattr("app.ai.service.anthropic.Anthropic", FakeClient)


def test_score_match_persists_score_and_logs_one_run(client: TestClient, monkeypatch) -> None:
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _fake_response(_score_json(score=82, part_time_fit=True))

    _install_fake_client(monkeypatch, create=create)

    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/score-match")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["score"] == 82
    assert body["part_time_fit"] is True
    assert body["reasons"]
    assert body["model"] == "claude-opus-5"
    assert body["run_id"] > 0

    # The reply was requested as structured JSON (tool-use/JSON structured output),
    # not free text scraped from prose.
    assert captured["output_config"]["format"]["type"] == "json_schema"

    # DoD: scoring EXPLICITLY weighs workload / weekly_hours / duration — the
    # availability signals must reach the model in the prompt.
    sent = json.dumps(captured["messages"])
    assert "part_time" in sent  # workload
    assert "10" in sent  # weekly_hours
    assert "one_to_three_months" in sent  # duration

    # The score is persisted on the job and surfaced by GET /api/jobs/{id}.
    got = client.get(f"/api/jobs/{job_id}").json()
    assert got["match_score"] == 82
    assert got["match_part_time_fit"] is True
    assert got["match_reasons"]
    assert got["match_scored_at"] is not None

    # Exactly one ai_run, feature score_match, linked to the job (via #34 helper).
    runs = client.get("/api/ai/runs", params={"feature": "score_match"}).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["job_id"] == job_id
    assert runs[0]["id"] == body["run_id"]


def test_score_match_weighs_availability_for_full_time_job(client: TestClient, monkeypatch) -> None:
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        # A full-time-leaning job should score low — the fake returns the verdict
        # the system prompt instructs; here we assert the *inputs* that drive it.
        return _fake_response(_score_json(score=15, reasons=["Full-time, ~40h/week"], part_time_fit=False))

    _install_fake_client(monkeypatch, create=create)

    job_id = client.post(
        "/api/jobs",
        json=_job_payload(
            url="https://example.test/jobs/ft",
            workload="full_time",
            weekly_hours=40,
            duration="ongoing",
        ),
    ).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/score-match")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["score"] == 15
    assert body["part_time_fit"] is False

    # The system prompt makes availability dominate skill match.
    system = captured["system"].lower()
    assert "part-time" in system
    assert "full-time" in system
    assert "outweigh" in system  # availability must outweigh skill match

    # The full-time availability signals are present for the model to weigh.
    sent = json.dumps(captured["messages"])
    assert "full_time" in sent
    assert "40" in sent
    assert "ongoing" in sent

    # The low score is persisted just like a high one.
    assert client.get(f"/api/jobs/{job_id}").json()["match_score"] == 15


def test_score_is_clamped_to_0_100(client: TestClient, monkeypatch) -> None:
    # Defensive: even if a reply slips past the schema bound, we clamp to 0–100.
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: _fake_response(_score_json(score=250)),
    )
    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    body = client.post(f"/api/jobs/{job_id}/score-match").json()
    assert body["score"] == 100


def test_score_match_missing_key_returns_503_and_leaves_job_unscored(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/score-match")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    # No call was attempted → nothing logged, and the job stays unscored.
    assert client.get("/api/ai/runs", params={"feature": "score_match"}).json() == []
    assert client.get(f"/api/jobs/{job_id}").json()["match_score"] is None


def test_score_match_upstream_failure_returns_502_and_logs_error(
    client: TestClient, monkeypatch
) -> None:
    def boom(**kwargs):
        raise RuntimeError("upstream exploded")

    _install_fake_client(monkeypatch, create=boom)
    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/score-match")
    assert resp.status_code == 502

    runs = client.get("/api/ai/runs", params={"feature": "score_match"}).json()
    assert len(runs) == 1  # a failure still logs exactly one row
    assert runs[0]["status"] == "error"
    assert "upstream exploded" in runs[0]["error"]
    # The job is not scored when the call fails.
    assert client.get(f"/api/jobs/{job_id}").json()["match_score"] is None


def test_score_match_non_json_reply_is_clean_502(client: TestClient, monkeypatch) -> None:
    # If the model ever returns unparseable output, surface a clean 502, not a 500,
    # and leave the job unscored.
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: _fake_response("not json at all"),
    )
    job_id = client.post("/api/jobs", json=_job_payload()).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/score-match")
    assert resp.status_code == 502
    assert client.get(f"/api/jobs/{job_id}").json()["match_score"] is None


def test_score_match_unknown_job_is_404_before_any_ai_call(client: TestClient, monkeypatch) -> None:
    # 404 must precede the AI call — a missing job costs nothing and logs nothing.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert client.post("/api/jobs/999999/score-match").status_code == 404
    assert client.get("/api/ai/runs", params={"feature": "score_match"}).json() == []
