# Pydantic request/response schemas — added in Phase 1.
from .ai import (
    AiRunRead,
    DraftProposalRequest,
    DraftProposalResponse,
    ScoreMatchResponse,
    SmokeRequest,
    SmokeResponse,
    TailorCvRequest,
    TailorCvResponse,
)
from .analytics import (
    AiAnalytics,
    AiDailySpend,
    AiFeatureCost,
    AnalyticsSummary,
    JobsAnalytics,
    MatchAnalytics,
    MatchBands,
    PipelineAnalytics,
)
from .application import ApplicationCard, ApplicationUpdate, JobSummary
from .cv import CvBase, CvCreate, CvRead, CvUpdate
from .job import ApplicationRead, JobBase, JobCreate, JobRead, JobUpdate
from .proposal import ProposalBase, ProposalCreate, ProposalRead, ProposalUpdate
from .saved_search import (
    SavedSearchBase,
    SavedSearchCreate,
    SavedSearchRead,
    SavedSearchRunResult,
    SavedSearchUpdate,
    SearchQuery,
)

__all__ = [
    "AiAnalytics",
    "AiDailySpend",
    "AiFeatureCost",
    "AiRunRead",
    "AnalyticsSummary",
    "ApplicationCard",
    "ApplicationRead",
    "ApplicationUpdate",
    "CvBase",
    "CvCreate",
    "CvRead",
    "CvUpdate",
    "DraftProposalRequest",
    "DraftProposalResponse",
    "JobBase",
    "JobCreate",
    "JobRead",
    "JobSummary",
    "JobUpdate",
    "JobsAnalytics",
    "MatchAnalytics",
    "MatchBands",
    "PipelineAnalytics",
    "ProposalBase",
    "ProposalCreate",
    "ProposalRead",
    "ProposalUpdate",
    "SavedSearchBase",
    "SavedSearchCreate",
    "SavedSearchRead",
    "SavedSearchRunResult",
    "SavedSearchUpdate",
    "SearchQuery",
    "ScoreMatchResponse",
    "SmokeRequest",
    "SmokeResponse",
    "TailorCvRequest",
    "TailorCvResponse",
]
