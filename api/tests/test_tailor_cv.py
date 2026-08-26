"""tailor_cv: markdown CV tailoring, persistence as a cv row, and ai_run logging.

Hermetic — the Anthropic client is monkeypatched with a fake, so no network hits
Anthropic. The fake records the request it receives, which lets us assert the DoD
directly: the base CV content and the job's availability signals reach the prompt,
the reply is asked for as markdown (no ``output_config`` — unlike score_match),
the tailored CV is saved as a ``cv`` row with ``job_id`` set, exactly one
``tailor_cv`` ai_run is logged (linked to the job), and there is a clear error
(400) when no base CV exists yet. The missing-key and upstream-failure paths stay
clean (503 / 502) and save nothing.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import settings

_TAILORED_MD = "## Summary\nSenior React engineer.\n\n## Skills\n- React\n- TypeScript\n"


def _job_payload(**overrides) -> dict:
    """A valid part-time job body; override any field for a specific case."""
    payload = {
        "url": "https://example.test/jobs/tailor",
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


def _fake_response(text: str, input_tokens: int = 200, output_tokens: int = 150):
    """A minimal stand-in for an anthropic Message: a thinking block then markdown."""
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


def _make_job(client: TestClient, **overrides) -> int:
    return client.post("/api/jobs", json=_job_payload(**overrides)).json()["id"]


def _make_base_cv(client: TestClient, label: str = "Master", content: str = "BASE-CV-MARKER") -> int:
    return client.post("/api/cvs", json={"label": label, "content": content}).json()["id"]


def test_tailor_cv_saves_tailored_cv_and_logs_one_run(client: TestClient, monkeypatch) -> None:
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _fake_response(_TAILORED_MD)

    _install_fake_client(monkeypatch, create=create)

    job_id = _make_job(client)
    base_cv_id = _make_base_cv(client, content="MASTER-CV-CONTENT with React history")

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["base_cv_id"] == base_cv_id
    assert body["cv_id"] > 0
    assert body["content"] == _TAILORED_MD.strip()
    assert body["label"].startswith("Tailored — ")
    assert body["model"] == "claude-opus-5"
    assert body["run_id"] > 0

    # The reply is markdown prose, NOT schema-constrained JSON — so unlike
    # score_match, tailor_cv must not send output_config.
    assert "output_config" not in captured

    # DoD: the base CV content and the job's availability signals (workload /
    # weekly_hours / duration) both reach the model in the prompt.
    sent = json.dumps(captured["messages"])
    assert "MASTER-CV-CONTENT" in sent  # base CV content
    assert "part_time" in sent  # workload
    assert "10" in sent  # weekly_hours
    assert "one_to_three_months" in sent  # duration

    # The system prompt enforces the part-time scope and truthful tailoring.
    system = captured["system"].lower()
    assert "part-time" in system
    assert "never invent" in system

    # The tailored CV is persisted as a cv row with job_id set and is retrievable.
    cv = client.get(f"/api/cvs/{body['cv_id']}").json()
    assert cv["job_id"] == job_id
    assert cv["content"] == _TAILORED_MD.strip()
    listed = client.get("/api/cvs", params={"job_id": job_id}).json()
    assert [c["id"] for c in listed] == [body["cv_id"]]

    # Exactly one ai_run, feature tailor_cv, linked to the job (via the #34 helper).
    runs = client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["job_id"] == job_id
    assert runs[0]["id"] == body["run_id"]


def test_tailor_cv_defaults_to_newest_base_cv(client: TestClient, monkeypatch) -> None:
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_TAILORED_MD),
    )

    job_id = _make_job(client)
    _make_base_cv(client, label="Old master", content="ALPHA-MASTER-CV")
    newest = _make_base_cv(client, label="New master", content="BETA-MASTER-CV")

    body = client.post(f"/api/jobs/{job_id}/tailor-cv").json()
    assert body["base_cv_id"] == newest

    sent = json.dumps(captured["messages"])
    assert "BETA-MASTER-CV" in sent
    assert "ALPHA-MASTER-CV" not in sent


def test_tailor_cv_uses_explicit_base_cv_id(client: TestClient, monkeypatch) -> None:
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_TAILORED_MD),
    )

    job_id = _make_job(client)
    chosen = _make_base_cv(client, label="Old master", content="ALPHA-MASTER-CV")
    _make_base_cv(client, label="New master", content="BETA-MASTER-CV")  # newer, not chosen

    body = client.post(f"/api/jobs/{job_id}/tailor-cv", json={"base_cv_id": chosen}).json()
    assert body["base_cv_id"] == chosen

    sent = json.dumps(captured["messages"])
    assert "ALPHA-MASTER-CV" in sent
    assert "BETA-MASTER-CV" not in sent


def test_tailor_cv_no_base_cv_returns_400_and_logs_nothing(client: TestClient, monkeypatch) -> None:
    # A valid key is set, but there is no base CV to tailor from → a clear 400 that
    # never reaches (or pays for) the AI call.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    job_id = _make_job(client)

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv")
    assert resp.status_code == 400
    assert "base cv" in resp.json()["detail"].lower()

    assert client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json() == []
    assert client.get("/api/cvs", params={"job_id": job_id}).json() == []


def test_tailor_cv_unknown_base_cv_id_is_404(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    job_id = _make_job(client)

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv", json={"base_cv_id": 999999})
    assert resp.status_code == 404
    assert client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json() == []


def test_tailor_cv_base_cv_id_must_be_a_base_cv(client: TestClient, monkeypatch) -> None:
    # A CV already tailored for a job (job_id set) is not a valid base to tailor
    # from → 422, before any AI call.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    job_id = _make_job(client)
    tailored_cv_id = client.post(
        "/api/cvs", json={"label": "Already tailored", "content": "x", "job_id": job_id}
    ).json()["id"]

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv", json={"base_cv_id": tailored_cv_id})
    assert resp.status_code == 422
    assert client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json() == []


def test_tailor_cv_missing_key_returns_503_and_saves_nothing(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    job_id = _make_job(client)
    _make_base_cv(client)

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    # No call was attempted → nothing logged, and no tailored CV was saved.
    assert client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json() == []
    assert client.get("/api/cvs", params={"job_id": job_id}).json() == []


def test_tailor_cv_upstream_failure_returns_502_and_logs_error(
    client: TestClient, monkeypatch
) -> None:
    def boom(**kwargs):
        raise RuntimeError("upstream exploded")

    _install_fake_client(monkeypatch, create=boom)
    job_id = _make_job(client)
    _make_base_cv(client)

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv")
    assert resp.status_code == 502

    runs = client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json()
    assert len(runs) == 1  # a failure still logs exactly one row
    assert runs[0]["status"] == "error"
    assert "upstream exploded" in runs[0]["error"]
    # Nothing is saved when the call fails.
    assert client.get("/api/cvs", params={"job_id": job_id}).json() == []


def test_tailor_cv_empty_reply_is_clean_502(client: TestClient, monkeypatch) -> None:
    # A blank/whitespace reply must surface a clean 502 (not a 500) and save no CV,
    # so an empty document is never persisted. The call itself completed, so one
    # success ai_run is still logged (the run happened) — mirrors score_match's
    # non-JSON path.
    _install_fake_client(monkeypatch, create=lambda **kw: _fake_response("   \n  "))
    job_id = _make_job(client)
    _make_base_cv(client)

    resp = client.post(f"/api/jobs/{job_id}/tailor-cv")
    assert resp.status_code == 502
    assert client.get("/api/cvs", params={"job_id": job_id}).json() == []


def test_tailor_cv_unknown_job_is_404_before_any_ai_call(
    client: TestClient, monkeypatch
) -> None:
    # 404 must precede the AI call — a missing job costs nothing and logs nothing.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert client.post("/api/jobs/999999/tailor-cv").status_code == 404
    assert client.get("/api/ai/runs", params={"feature": "tailor_cv"}).json() == []
