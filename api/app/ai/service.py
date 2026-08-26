"""The single Claude entry point for JobDesk's AI layer.

Every AI feature (``score_match`` / ``tailor_cv`` / ``draft_proposal``) calls
:func:`call_claude`, which wraps the Anthropic Messages API and writes **exactly
one** :class:`~app.models.AiRun` row per call — success *and* failure — so token
spend is always accountable. The model and API key come from
:mod:`app.config`; callers may override the model / token ceiling per call.

Error contract (routers map these; a missing key is never a 500 stack trace):

* :class:`AIConfigError` — the layer is not configured (no API key). Raised
  *before* any network call, so no ``ai_run`` row is written. Maps to **503**.
* :class:`AIServiceError` — the call was attempted but the upstream API failed.
  An ``ai_run`` row with ``status='error'`` is written first. Maps to **502**.
"""
from __future__ import annotations

from dataclasses import dataclass

import anthropic
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AiRun

# Price per 1M tokens in USD as (input, output). Source: the `claude-api` skill's
# current-models table. Unknown models price at 0.0 (recorded, never crashing).
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

_ERROR_SUMMARY_MAX = 2000


class AIError(RuntimeError):
    """Base class for AI-layer failures."""


class AIConfigError(AIError):
    """The AI layer is not configured (e.g. ANTHROPIC_API_KEY unset) — maps to 503."""


class AIServiceError(AIError):
    """An attempted Claude call failed upstream — maps to 502 (ai_run recorded)."""


@dataclass
class ClaudeResult:
    """A successful call's answer plus its accounting."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    stop_reason: str | None
    run: AiRun


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimate a call's USD cost from token usage and per-model pricing.

    Cache writes bill at ~1.25x input and cache reads at ~0.1x input; both are
    zero unless prompt caching is in use. Unknown models yield 0.0.
    """
    input_price, output_price = PRICING.get(model, (0.0, 0.0))
    cost = (
        input_tokens / 1_000_000 * input_price
        + output_tokens / 1_000_000 * output_price
        + cache_creation_tokens / 1_000_000 * input_price * 1.25
        + cache_read_tokens / 1_000_000 * input_price * 0.10
    )
    return round(cost, 6)


def _record_run(db: Session, **fields) -> AiRun:
    """Persist one ai_run row and commit it, so the cost record is durable."""
    run = AiRun(**fields)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _summarize_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:_ERROR_SUMMARY_MAX]


def call_claude(
    db: Session,
    feature: str,
    prompt: str | None = None,
    *,
    system: str | None = None,
    messages: list[dict] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    job_id: int | None = None,
) -> ClaudeResult:
    """Call Claude once and log the run; return the text answer and its cost.

    Pass either ``prompt`` (wrapped as a single user turn) or a full ``messages``
    list. ``model`` / ``max_tokens`` default to the app config. Adaptive thinking
    is enabled (Claude decides how much to reason), which assumes a current-gen
    thinking-capable model such as the ``claude-opus-5`` default.

    Raises :class:`AIConfigError` if no API key is set (no row written) and
    :class:`AIServiceError` if the upstream call fails (an error row is written).
    """
    if not settings.anthropic_api_key:
        raise AIConfigError("ANTHROPIC_API_KEY is not set; the AI layer is disabled.")

    model = model or settings.anthropic_model
    max_tokens = max_tokens or settings.anthropic_max_tokens

    if messages is None:
        if prompt is None:
            raise ValueError("call_claude requires either 'prompt' or 'messages'.")
        messages = [{"role": "user", "content": prompt}]

    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "thinking": {"type": "adaptive"},
    }
    if system is not None:
        request["system"] = system

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(**request)
    except Exception as exc:  # log every failure as a run, then surface it as a 502
        _record_run(
            db,
            feature=feature,
            model=model,
            status="error",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=_summarize_error(exc),
            job_id=job_id,
        )
        raise AIServiceError(f"Claude call failed: {_summarize_error(exc)}") from exc

    usage = response.usage
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    used_model = response.model or model
    cost = estimate_cost_usd(used_model, input_tokens, output_tokens, cache_creation, cache_read)

    text = "".join(block.text for block in response.content if block.type == "text")

    run = _record_run(
        db,
        feature=feature,
        model=used_model,
        status="success",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None,
        job_id=job_id,
    )
    return ClaudeResult(
        text=text,
        model=used_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        stop_reason=response.stop_reason,
        run=run,
    )
