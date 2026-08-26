"""The AI foundation: cost math, the ai_run ledger, and the call_claude contract.

Everything here is hermetic — no network to Anthropic. The two paths that would
otherwise call the API (smoke success / failure) monkeypatch the Anthropic client
with a fake, so we can assert the DoD invariant directly: every attempted Claude
call writes exactly one ai_run row, and a missing key is a clean 503, not a 500.
"""
from types import SimpleNamespace

from app.ai.service import estimate_cost_usd
from app.config import settings
from app.models import AiRun


# --- pure cost function -------------------------------------------------------


def test_estimate_cost_uses_per_model_pricing() -> None:
    # Opus 5 is $5 / $25 per 1M tokens: 100 in + 20 out.
    cost = estimate_cost_usd("claude-opus-5", 100, 20)
    assert cost == round(100 / 1_000_000 * 5.0 + 20 / 1_000_000 * 25.0, 6)


def test_estimate_cost_unknown_model_is_zero_not_error() -> None:
    assert estimate_cost_usd("some-future-model", 1000, 1000) == 0.0


# --- ai_run model round-trip --------------------------------------------------


def test_ai_run_round_trip(db_session) -> None:
    run = AiRun(
        feature="score_match",
        model="claude-opus-5",
        status="success",
        input_tokens=120,
        output_tokens=30,
        cost_usd=0.00135,
    )
    db_session.add(run)
    db_session.flush()

    assert run.id is not None
    assert run.job_id is None  # nullable — a run need not reference a job
    assert run.error is None


# --- GET /api/ai/runs ---------------------------------------------------------


def _add_run(db, **overrides) -> AiRun:
    fields = {"feature": "smoke", "model": "claude-opus-5", "status": "success"}
    fields.update(overrides)
    run = AiRun(**fields)
    db.add(run)
    db.flush()
    return run


def test_list_runs_newest_first_with_filters(client, db_session) -> None:
    _add_run(db_session, feature="score_match", status="success")
    _add_run(db_session, feature="tailor_cv", status="error", error="boom")
    last = _add_run(db_session, feature="score_match", status="success")

    listed = client.get("/api/ai/runs").json()
    assert len(listed) == 3
    # created_at ties within one transaction, so id desc decides: newest first.
    assert listed[0]["id"] == last.id

    by_feature = client.get("/api/ai/runs", params={"feature": "score_match"}).json()
    assert {r["feature"] for r in by_feature} == {"score_match"}
    assert len(by_feature) == 2

    by_status = client.get("/api/ai/runs", params={"status": "error"}).json()
    assert {r["status"] for r in by_status} == {"error"}
    assert by_status[0]["error"] == "boom"


# --- POST /api/ai/smoke: the call_claude contract -----------------------------


def _fake_response(text: str = "pong", input_tokens: int = 100, output_tokens: int = 20):
    """A minimal stand-in for an anthropic Message (only the fields we read)."""
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


def test_smoke_missing_key_returns_503_and_logs_nothing(client, monkeypatch) -> None:
    # No key configured: a config error, never a 500 — and no call was made,
    # so nothing is logged to the ledger.
    monkeypatch.setattr(settings, "anthropic_api_key", None)

    resp = client.post("/api/ai/smoke", json={"prompt": "hi"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    assert client.get("/api/ai/runs").json() == []


def test_smoke_success_logs_exactly_one_run(client, monkeypatch) -> None:
    _install_fake_client(monkeypatch, create=lambda **kw: _fake_response())

    resp = client.post("/api/ai/smoke", json={"prompt": "ping"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["text"] == "pong"  # thinking block filtered, only text returned
    assert body["cost_usd"] == round(100 / 1_000_000 * 5.0 + 20 / 1_000_000 * 25.0, 6)

    runs = client.get("/api/ai/runs").json()
    assert len(runs) == 1
    assert runs[0]["feature"] == "smoke"
    assert runs[0]["status"] == "success"
    assert runs[0]["input_tokens"] == 100
    assert runs[0]["output_tokens"] == 20
    assert runs[0]["id"] == body["run_id"]


def test_smoke_upstream_failure_returns_502_and_logs_error_run(client, monkeypatch) -> None:
    def boom(**kwargs):
        raise RuntimeError("upstream exploded")

    _install_fake_client(monkeypatch, create=boom)

    resp = client.post("/api/ai/smoke", json={"prompt": "ping"})
    assert resp.status_code == 502

    runs = client.get("/api/ai/runs").json()
    assert len(runs) == 1  # a failure still logs exactly one row
    assert runs[0]["status"] == "error"
    assert "upstream exploded" in runs[0]["error"]
    assert runs[0]["cost_usd"] == 0.0
