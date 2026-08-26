from .base import JobProvider, NormalizedJob
from .capture import CaptureProvider
from .manual import ManualProvider
from .upwork import UpworkProvider

__all__ = [
    "CaptureProvider",
    "JobProvider",
    "ManualProvider",
    "NormalizedJob",
    "UpworkProvider",
]
