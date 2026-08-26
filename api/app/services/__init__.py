"""Service layer: reusable write-paths that sit above the ORM.

The ingestion service is the shared upsert/dedupe used by every job source
(browser capture, the Upwork poller), keeping providers out of the persistence
details.
"""
from .ingest import IngestSummary, ingest_jobs

__all__ = ["IngestSummary", "ingest_jobs"]
