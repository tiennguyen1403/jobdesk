from __future__ import annotations

from .base import JobProvider, NormalizedJob


class ManualProvider(JobProvider):
    """Turn hand-entered job data into the app's normalized shape.

    Manual entry is the always-available ingestion path: the Upwork API needs
    approval and can't be relied on, so a user must be able to add a job by hand
    and have it behave exactly like one from any other source. The "source" here
    is simply whatever the user typed, so :meth:`fetch` maps that input onto
    :class:`NormalizedJob` without any network I/O.

    It accepts one job (a plain mapping of fields) or several
    (``{"jobs": [ {...}, {...} ]}``) and returns them normalized. The untouched
    input is preserved in each job's ``raw`` for audit / later re-parsing.
    """

    key = "manual"
    supports_polling = False

    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        if not search:
            return []
        items = search["jobs"] if isinstance(search.get("jobs"), list) else [search]
        return [self._normalize(item) for item in items]

    @staticmethod
    def _normalize(item: dict) -> NormalizedJob:
        data = dict(item)
        # Keep the original input verbatim so nothing the user entered is lost.
        data.setdefault("raw", dict(item))
        return NormalizedJob(**data)
