# Register ORM models here so Alembic autogenerate can see them.
from .ai_run import AiRun
from .application import Application, ApplicationStatus
from .job import Job

__all__ = ["AiRun", "Application", "ApplicationStatus", "Job"]
