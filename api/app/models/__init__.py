# Register ORM models here so Alembic autogenerate can see them.
from .ai_run import AiRun
from .application import Application, ApplicationStatus
from .cv import Cv
from .job import Job
from .proposal import Proposal
from .saved_search import SavedSearch
from .upwork_token import UpworkToken

__all__ = [
    "AiRun",
    "Application",
    "ApplicationStatus",
    "Cv",
    "Job",
    "Proposal",
    "SavedSearch",
    "UpworkToken",
]
