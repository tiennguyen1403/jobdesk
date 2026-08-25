from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class NormalizedJob(BaseModel):
    """Định dạng job chuẩn hoá — mọi provider đều trả về shape này.

    Nhờ vậy phần pipeline / CV / AI / UI không quan tâm job đến từ đâu
    (Manual, Browser Capture, Upwork API, Freelancer.com, ...).
    """

    external_id: str | None = None      # id trên nền tảng gốc (None nếu nhập tay)
    url: str
    title: str
    description: str = ""

    budget_type: str = "fixed"          # 'hourly' | 'fixed'
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "USD"

    # --- Ràng buộc "làm thêm": chỉ nhắm job part-time / theo giờ / theo dự án ---
    workload: str | None = None         # 'part_time' | 'full_time'
    weekly_hours: int | None = None     # số giờ/tuần ước tính (lọc job hợp lịch tối & cuối tuần)
    duration: str | None = None         # ví dụ: 'less_than_1_month' | 'one_to_three_months' | 'ongoing'

    skills: list[str] = []
    client_country: str | None = None
    posted_at: datetime | None = None

    raw: dict = {}                      # payload gốc (audit / parse lại sau)


class JobProvider(ABC):
    """Interface cắm-rút cho mọi nguồn job."""

    key: str = "base"                   # 'manual' | 'capture' | 'upwork' | ...
    supports_polling: bool = False      # True nếu có thể poll định kỳ (APScheduler)

    @abstractmethod
    def fetch(self, search: dict | None = None) -> list[NormalizedJob]:
        """Trả về danh sách job đã chuẩn hoá."""
        ...
