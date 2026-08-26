"""AI layer: a single Claude entry point with per-call cost logging (Phase 2)."""
from .service import (
    AIConfigError,
    AIError,
    AIServiceError,
    ClaudeResult,
    MatchScore,
    TailoredCv,
    call_claude,
    estimate_cost_usd,
    score_match,
    tailor_cv,
)

__all__ = [
    "AIConfigError",
    "AIError",
    "AIServiceError",
    "ClaudeResult",
    "MatchScore",
    "TailoredCv",
    "call_claude",
    "estimate_cost_usd",
    "score_match",
    "tailor_cv",
]
