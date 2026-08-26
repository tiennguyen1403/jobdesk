# Register ORM models here so Alembic autogenerate can see them.
from .application import Application, ApplicationStatus
from .job import Job

__all__ = ["Application", "ApplicationStatus", "Job"]
