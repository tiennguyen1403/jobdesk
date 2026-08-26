"""draft_proposal: markdown proposal drafting, persistence as a proposal row, logging.

Hermetic — the Anthropic client is monkeypatched with a fake, so no network hits
Anthropic. The fake records the request it receives, which lets us assert the DoD
directly: the job's availability signals and the grounding CV reach the prompt, the
reply is asked for as markdown prose (no ``output_config`` — unlike score_match),
the system prompt enforces the part-time scope and the draft-only rule (JobDesk
never submits), the draft is saved as a ``proposal`` row and is editable via the
#36 endpoints, and exactly one ``draft_proposal`` ai_run is logged (linked to the
job). Unlike tailor_cv, a proposal can be drafted with NO CV at all. The
missing-key and upstream-failure paths stay clean (503 / 502) and save nothing.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import settings

_PROPOSAL_MD = (
    "Hi there,\n\nI can take this on in the evenings and on weekends. "
    "I've shipped React apps and would love to help.\n\nBest,\nA freelancer\n"
)


def _job_payload(**overrides) -> dict:
    """A valid part-time job body; override any field for a specific case."""
    payload = {
        "url": "https://example.test/jobs/proposal",
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


def _fake_response(text: str, input_tokens: int = 220, output_tokens: int = 160):
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


def _make_cv(client: TestClient, label: str, content: str, job_id: int | None = None) -> int:
    body = {"label": label, "content": content}
    if job_id is not None:
        body["job_id"] = job_id
    return client.post("/api/cvs", json=body).json()["id"]


def test_draft_proposal_saves_proposal_and_logs_one_run(client: TestClient, monkeypatch) -> None:
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _fake_response(_PROPOSAL_MD)

    _install_fake_client(monkeypatch, create=create)

    job_id = _make_job(client)
    cv_id = _make_cv(client, "Master", "MASTER-CV-CONTENT with React history")

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["cv_id"] == cv_id
    assert body["proposal_id"] > 0
    assert body["content"] == _PROPOSAL_MD.strip()
    assert body["model"] == "claude-opus-5"
    assert body["run_id"] > 0

    # The reply is markdown prose, NOT schema-constrained JSON — so unlike
    # score_match, draft_proposal must not send output_config.
    assert "output_config" not in captured

    # DoD: the job's availability signals (workload / weekly_hours / duration) and
    # the grounding CV content both reach the model in the prompt.
    sent = json.dumps(captured["messages"])
    assert "MASTER-CV-CONTENT" in sent  # CV content
    assert "part_time" in sent  # workload
    assert "10" in sent  # weekly_hours
    assert "one_to_three_months" in sent  # duration

    # The system prompt enforces the part-time scope, truthful grounding, and the
    # draft-only rule (JobDesk never submits).
    system = captured["system"].lower()
    assert "part-time" in system
    assert "evenings and on weekends" in system
    assert "never invent" in system
    assert "draft only" in system  # never auto-submits

    # The draft is persisted as a proposal row for the job and is retrievable and
    # editable via the #36 proposal endpoints.
    got = client.get(f"/api/proposals/{body['proposal_id']}").json()
    assert got["job_id"] == job_id
    assert got["content"] == _PROPOSAL_MD.strip()
    listed = client.get("/api/proposals", params={"job_id": job_id}).json()
    assert [p["id"] for p in listed] == [body["proposal_id"]]

    # Exactly one ai_run, feature draft_proposal, linked to the job (via #34 helper).
    runs = client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["job_id"] == job_id
    assert runs[0]["id"] == body["run_id"]


def test_draft_proposal_prefers_cv_tailored_for_this_job(client: TestClient, monkeypatch) -> None:
    # With no cv_id, a CV already tailored for THIS job wins over the base CV.
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_PROPOSAL_MD),
    )

    job_id = _make_job(client)
    _make_cv(client, "Master", "BASE-CV-CONTENT")  # base CV, not preferred
    tailored_id = _make_cv(client, "Tailored", "TAILORED-FOR-JOB", job_id=job_id)

    body = client.post(f"/api/jobs/{job_id}/draft-proposal").json()
    assert body["cv_id"] == tailored_id

    sent = json.dumps(captured["messages"])
    assert "TAILORED-FOR-JOB" in sent
    assert "BASE-CV-CONTENT" not in sent


def test_draft_proposal_defaults_to_newest_base_cv(client: TestClient, monkeypatch) -> None:
    # With no cv_id and no job-tailored CV, the newest base CV is used.
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_PROPOSAL_MD),
    )

    job_id = _make_job(client)
    _make_cv(client, "Old master", "ALPHA-MASTER-CV")
    newest = _make_cv(client, "New master", "BETA-MASTER-CV")

    body = client.post(f"/api/jobs/{job_id}/draft-proposal").json()
    assert body["cv_id"] == newest

    sent = json.dumps(captured["messages"])
    assert "BETA-MASTER-CV" in sent
    assert "ALPHA-MASTER-CV" not in sent


def test_draft_proposal_uses_explicit_cv_id(client: TestClient, monkeypatch) -> None:
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_PROPOSAL_MD),
    )

    job_id = _make_job(client)
    chosen = _make_cv(client, "Old master", "ALPHA-MASTER-CV")
    _make_cv(client, "New master", "BETA-MASTER-CV")  # newer, not chosen

    body = client.post(f"/api/jobs/{job_id}/draft-proposal", json={"cv_id": chosen}).json()
    assert body["cv_id"] == chosen

    sent = json.dumps(captured["messages"])
    assert "ALPHA-MASTER-CV" in sent
    assert "BETA-MASTER-CV" not in sent


def test_draft_proposal_works_without_any_cv(client: TestClient, monkeypatch) -> None:
    # Unlike tailor_cv (which needs a base CV → 400), a proposal can be drafted with
    # no CV at all: it still succeeds and grounds nothing.
    captured: dict = {}
    _install_fake_client(
        monkeypatch,
        create=lambda **kw: captured.update(kw) or _fake_response(_PROPOSAL_MD),
    )

    job_id = _make_job(client)  # no CVs exist

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["cv_id"] is None
    assert body["content"] == _PROPOSAL_MD.strip()

    # The prompt tells the model no CV was provided (so it keeps claims general),
    # and the availability signals are still present.
    sent = json.dumps(captured["messages"])
    assert "no CV provided" in sent
    assert "part_time" in sent

    # The draft is still saved and one run is logged.
    assert client.get("/api/proposals", params={"job_id": job_id}).json()[0]["id"] == body["proposal_id"]
    runs = client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"


def test_draft_proposal_unknown_cv_id_is_404_and_logs_nothing(client: TestClient, monkeypatch) -> None:
    # A given but missing cv_id is a clean 404 that never reaches (or pays for) the
    # AI call and saves nothing.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    job_id = _make_job(client)

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal", json={"cv_id": 999999})
    assert resp.status_code == 404

    assert client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json() == []
    assert client.get("/api/proposals", params={"job_id": job_id}).json() == []


def test_draft_proposal_missing_key_returns_503_and_saves_nothing(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    job_id = _make_job(client)
    _make_cv(client, "Master", "MASTER-CV")

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    # No call was attempted → nothing logged, and no proposal was saved.
    assert client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json() == []
    assert client.get("/api/proposals", params={"job_id": job_id}).json() == []


def test_draft_proposal_upstream_failure_returns_502_and_logs_error(
    client: TestClient, monkeypatch
) -> None:
    def boom(**kwargs):
        raise RuntimeError("upstream exploded")

    _install_fake_client(monkeypatch, create=boom)
    job_id = _make_job(client)
    _make_cv(client, "Master", "MASTER-CV")

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal")
    assert resp.status_code == 502

    runs = client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json()
    assert len(runs) == 1  # a failure still logs exactly one row
    assert runs[0]["status"] == "error"
    assert "upstream exploded" in runs[0]["error"]
    # Nothing is saved when the call fails.
    assert client.get("/api/proposals", params={"job_id": job_id}).json() == []


def test_draft_proposal_empty_reply_is_clean_502(client: TestClient, monkeypatch) -> None:
    # A blank/whitespace reply must surface a clean 502 (not a 500) and save no
    # proposal, so an empty draft is never persisted. The call itself completed, so
    # one success ai_run is still logged — mirrors tailor_cv's empty-reply path.
    _install_fake_client(monkeypatch, create=lambda **kw: _fake_response("   \n  "))
    job_id = _make_job(client)
    _make_cv(client, "Master", "MASTER-CV")

    resp = client.post(f"/api/jobs/{job_id}/draft-proposal")
    assert resp.status_code == 502
    assert client.get("/api/proposals", params={"job_id": job_id}).json() == []


def test_draft_proposal_unknown_job_is_404_before_any_ai_call(
    client: TestClient, monkeypatch
) -> None:
    # 404 must precede the AI call — a missing job costs nothing and logs nothing.
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert client.post("/api/jobs/999999/draft-proposal").status_code == 404
    assert client.get("/api/ai/runs", params={"feature": "draft_proposal"}).json() == []
