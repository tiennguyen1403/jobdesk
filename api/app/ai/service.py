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

import json
from dataclasses import dataclass
from typing import Any

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
    output_config: dict | None = None,
    job_id: int | None = None,
) -> ClaudeResult:
    """Call Claude once and log the run; return the text answer and its cost.

    Pass either ``prompt`` (wrapped as a single user turn) or a full ``messages``
    list. ``model`` / ``max_tokens`` default to the app config. Adaptive thinking
    is enabled (Claude decides how much to reason), which assumes a current-gen
    thinking-capable model such as the ``claude-opus-5`` default.

    Pass ``output_config`` (e.g. ``{"format": {"type": "json_schema", ...}}``) to
    constrain the reply to a schema; the API then guarantees the text block is
    valid JSON, so callers can ``json.loads(result.text)`` without prompt-parsing.

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
    if output_config is not None:
        request["output_config"] = output_config

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


# --- score_match: part-time / evenings-and-weekends fit scoring --------------
#
# JobDesk only tracks side work for evenings and weekends — never full-time — so
# *availability* is the dominant scoring factor, above skill match. The score is
# produced as structured JSON (Claude's ``output_config`` json_schema format), so
# the shape is guaranteed and never scraped out of prose.

# Reply schema: an integer 0–100, a short list of reasons, and a part-time flag.
_SCORE_MATCH_FORMAT: dict[str, Any] = {
    "format": {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 6,
                },
                "part_time_fit": {"type": "boolean"},
            },
            "required": ["score", "reasons", "part_time_fit"],
            "additionalProperties": False,
        },
    }
}

_SCORE_MATCH_SYSTEM = (
    "You score how well a freelance job fits ONE specific freelancer who can only take "
    "part-time, hourly, or project-based side work in the evenings and on weekends — never "
    "a full-time commitment.\n\n"
    "Return an integer score from 0 to 100: 100 is an ideal evenings-and-weekends side gig, "
    "0 is unworkable. Availability is the DOMINANT factor and must outweigh skill match:\n"
    "- A job that leans full-time, needs more than ~20 hours/week, or requires weekday "
    "business-hours availability scores LOW (usually under 30) even if the skills match "
    "perfectly.\n"
    "- Favor a part_time workload, low weekly_hours (roughly 20 or fewer), and flexible, "
    "short, or project-based durations.\n"
    "- When workload, weekly_hours, or duration are unknown, stay cautious and say so in the "
    "reasons rather than assuming a good fit.\n\n"
    "Set part_time_fit to true only when the job is realistically doable alongside a "
    "full-time day job. Give 2–5 short, concrete reasons that reference the availability "
    "signals (workload / weekly hours / duration) as well as the skill fit."
)

# Keep the description bounded so one huge posting can't blow up token cost.
_DESCRIPTION_CHAR_CAP = 4000


def _job_facts(job: Any) -> str:
    """Render the job fields the model should weigh into a compact prompt.

    Reads attributes by name so it works with either an ORM :class:`~app.models.Job`
    or a :class:`~app.providers.base.NormalizedJob`. The availability signals
    (workload / weekly_hours / duration) lead, because they drive the score.
    """

    def budget() -> str:
        lo, hi = getattr(job, "budget_min", None), getattr(job, "budget_max", None)
        currency = getattr(job, "currency", None) or "USD"
        btype = getattr(job, "budget_type", None) or "unknown"
        if lo is None and hi is None:
            return f"{btype} (unspecified)"
        span = f"{lo}–{hi}" if lo is not None and hi is not None else (lo if hi is None else hi)
        return f"{btype} {span} {currency}"

    weekly = getattr(job, "weekly_hours", None)
    skills = getattr(job, "skills", None) or []
    description = (getattr(job, "description", None) or "").strip()
    if len(description) > _DESCRIPTION_CHAR_CAP:
        description = description[:_DESCRIPTION_CHAR_CAP] + " …[truncated]"

    lines = [
        f"Title: {getattr(job, 'title', None) or '(untitled)'}",
        f"Workload: {getattr(job, 'workload', None) or 'unknown'}",
        f"Weekly hours: {weekly if weekly is not None else 'unknown'}",
        f"Duration: {getattr(job, 'duration', None) or 'unknown'}",
        f"Budget: {budget()}",
        f"Skills: {', '.join(skills) if skills else 'none listed'}",
        f"Client country: {getattr(job, 'client_country', None) or 'unknown'}",
        f"Description: {description or '(none)'}",
    ]
    return "\n".join(lines)


@dataclass
class MatchScore:
    """A job's part-time fit as scored by Claude, plus the call's accounting."""

    score: int
    reasons: list[str]
    part_time_fit: bool
    result: ClaudeResult


def _parse_score(text: str) -> tuple[int, list[str], bool]:
    """Parse and defensively normalize the structured score reply.

    ``output_config`` already constrains the shape, but we clamp the score to
    0–100 and coerce types so a malformed reply degrades gracefully. Unparseable
    JSON is surfaced as an :class:`AIServiceError` (502), never a 500.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AIServiceError(
            f"score_match returned non-JSON output: {text[:200]!r}"
        ) from exc

    try:
        score = int(data["score"])
    except (KeyError, TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    reasons = [str(r) for r in (data.get("reasons") or [])]
    part_time_fit = bool(data.get("part_time_fit", False))
    return score, reasons, part_time_fit


def score_match(db: Session, job: Any, *, model: str | None = None) -> MatchScore:
    """Score how well ``job`` fits as a part-time / evenings-and-weekends side gig.

    Calls Claude with a schema-constrained reply and logs the run to ``ai_run``
    (``feature='score_match'``, linked to the job). Returns the parsed score,
    reasons, and part-time flag alongside the underlying :class:`ClaudeResult`
    so callers can surface the cost. Propagates :class:`AIConfigError` (503) and
    :class:`AIServiceError` (502) unchanged.
    """
    prompt = (
        "Score this job for a freelancer who is only free evenings and weekends. "
        "Weigh availability (workload / weekly hours / duration) above skill match.\n\n"
        f"{_job_facts(job)}"
    )
    result = call_claude(
        db,
        feature="score_match",
        prompt=prompt,
        system=_SCORE_MATCH_SYSTEM,
        model=model,
        output_config=_SCORE_MATCH_FORMAT,
        job_id=getattr(job, "id", None),
    )
    score, reasons, part_time_fit = _parse_score(result.text)
    return MatchScore(score=score, reasons=reasons, part_time_fit=part_time_fit, result=result)


# --- tailor_cv: rewrite the base CV to emphasize a job's relevant skills ------
#
# Unlike score_match, the output is not structured JSON but the CV document
# itself — well-formed **markdown** that is saved verbatim into a ``cv`` row. So
# there is no ``output_config``; the shape is prose, guided by the system prompt.
# The part-time scope is enforced in the prompt (frame for evenings/weekends,
# never imply full-time), and the model is told to tailor truthfully — reorder
# and emphasize what the base CV already supports, never invent experience.

_TAILOR_CV_SYSTEM = (
    "You tailor a freelancer's master CV to one specific freelance job.\n\n"
    "Rewrite and re-order the CV so the skills, experience, and achievements most "
    "relevant to THIS job lead. Keep it strictly truthful: you may rephrase, "
    "prioritize, trim, and emphasize, but you must NEVER invent employers, job "
    "titles, dates, skills, certifications, or achievements that the base CV does "
    "not already support.\n\n"
    "This freelancer only takes part-time, hourly, or project-based side work in the "
    "evenings and on weekends — never a full-time role. Frame availability and "
    "positioning accordingly and do not imply full-time availability.\n\n"
    "Return ONLY the tailored CV as clean, well-structured Markdown: use headings "
    "(## / ###), short paragraphs, and bullet lists. Begin directly with the CV — "
    "no preamble, no closing commentary, and no surrounding code fences."
)

# A CV is a document, not a one-line verdict: give adaptive thinking and the full
# CV room so the markdown is never truncated mid-section. The foundation's 4096
# default is tuned for short structured replies (e.g. score_match), so raise it.
_TAILOR_CV_MAX_TOKENS = 8000

# Bound the base CV the same way _job_facts bounds a job description, so one huge
# pasted CV can't blow up token cost.
_BASE_CV_CHAR_CAP = 12000


@dataclass
class TailoredCv:
    """A job-tailored CV (structured markdown) plus the call's accounting."""

    content: str
    result: ClaudeResult


def tailor_cv(db: Session, base_cv: Any, job: Any, *, model: str | None = None) -> TailoredCv:
    """Tailor ``base_cv`` to ``job`` with Claude and log the run to ``ai_run``.

    ``base_cv`` supplies the source (its ``content`` markdown) and ``job`` the
    target, rendered via :func:`_job_facts` so the part-time availability signals
    (workload / weekly hours / duration) reach the model. The reply is a complete
    tailored CV in markdown, returned as-is for the caller to persist as a
    tailored ``cv`` row (``feature='tailor_cv'``, linked to the job).

    Propagates :class:`AIConfigError` (503) and :class:`AIServiceError` (502)
    unchanged. An empty reply is surfaced as a 502 rather than silently saved as a
    blank CV.
    """
    base_content = (getattr(base_cv, "content", None) or "").strip()
    if len(base_content) > _BASE_CV_CHAR_CAP:
        base_content = base_content[:_BASE_CV_CHAR_CAP] + " …[truncated]"

    prompt = (
        "Tailor this freelancer's master CV to the target job below. Emphasize the "
        "skills and experience relevant to the job, stay truthful to the master CV, "
        "and keep the part-time / evenings-and-weekends scope in mind.\n\n"
        "=== MASTER CV (Markdown) ===\n"
        f"{base_content or '(the master CV is empty)'}\n\n"
        "=== TARGET JOB ===\n"
        f"{_job_facts(job)}"
    )
    result = call_claude(
        db,
        feature="tailor_cv",
        prompt=prompt,
        system=_TAILOR_CV_SYSTEM,
        model=model,
        max_tokens=_TAILOR_CV_MAX_TOKENS,
        job_id=getattr(job, "id", None),
    )
    content = result.text.strip()
    if not content:
        raise AIServiceError("tailor_cv returned empty content.")
    return TailoredCv(content=content, result=result)
