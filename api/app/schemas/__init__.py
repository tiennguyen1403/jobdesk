# Pydantic request/response schemas — added in Phase 1.
from .ai import (
    AiRunRead,
    ScoreMatchResponse,
    SmokeRequest,
    SmokeResponse,
    TailorCvRequest,
    TailorCvResponse,
)
from .application import ApplicationCard, ApplicationUpdate, JobSummary
from .cv import CvBase, CvCreate, CvRead, CvUpdate
from .job import ApplicationRead, JobBase, JobCreate, JobRead, JobUpdate
from .proposal import ProposalBase, ProposalCreate, ProposalRead, ProposalUpdate

__all__ = [
    "AiRunRead",
    "ApplicationCard",
    "ApplicationRead",
    "ApplicationUpdate",
    "CvBase",
    "CvCreate",
    "CvRead",
    "CvUpdate",
    "JobBase",
    "JobCreate",
    "JobRead",
    "JobSummary",
    "JobUpdate",
    "ProposalBase",
    "ProposalCreate",
    "ProposalRead",
    "ProposalUpdate",
    "ScoreMatchResponse",
    "SmokeRequest",
    "SmokeResponse",
    "TailorCvRequest",
    "TailorCvResponse",
]
