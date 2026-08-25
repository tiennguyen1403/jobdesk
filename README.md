# JobDesk

App quản lý job freelance cá nhân — gom job, quản lý pipeline apply (Kanban), dựng CV & proposal khớp từng job. Bắt đầu với Upwork, mở rộng sau.

> **Phạm vi:** chỉ nhắm job **part-time / theo giờ / theo dự án** (làm thêm buổi tối & cuối tuần). Không nhắm job full-time.

📋 Kế hoạch chi tiết (kiến trúc, data model, roadmap): xem **blueprint** — https://claude.ai/code/artifact/0bb986b5-66fd-495e-bed7-9d7dcc81cec5

---

## Stack

| Layer | Công nghệ |
|---|---|
| Frontend | Vite + React + TypeScript, Tailwind, TanStack Query |
| Backend | FastAPI (Python), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 |
| Hạ tầng | Docker Compose |
| AI (Phase 2) | Claude API |

## Chạy nhanh (Phase 0 — skeleton)

```bash
# 1. Tạo file .env từ mẫu
cp .env.example .env        # PowerShell: Copy-Item .env.example .env

# 2. Chạy toàn bộ (db + api + web)
docker compose up --build
```

Sau khi lên (cổng API mặc định `8000`; **máy này đang dùng `API_PORT=8001`** vì 8000 đã bị Docker khác chiếm):
- **Web:**  http://localhost:5173  — Dashboard hiển thị trạng thái kết nối API & DB
- **API:**  http://localhost:8001  — API docs tự sinh tại http://localhost:8001/docs
- **Health:** http://localhost:8001/api/health → `{"status":"ok","db":true}`

> **Đổi cổng API:** sửa `API_PORT` và `VITE_API_BASE` trong `.env` cho khớp (ví dụ 8000 nếu máy bạn còn trống).

## Cấu trúc

```
job-management/
├── docker-compose.yml
├── .env.example
├── api/                 # FastAPI
│   ├── app/
│   │   ├── main.py          # khởi tạo app + CORS + router
│   │   ├── config.py        # settings (pydantic-settings)
│   │   ├── db.py            # SQLAlchemy engine/session/Base
│   │   ├── routers/         # health.py (+ jobs, applications... ở Phase 1)
│   │   ├── models/          # ORM models (Phase 1)
│   │   ├── schemas/         # Pydantic schemas (Phase 1)
│   │   ├── providers/       # base.py: JobProvider + NormalizedJob
│   │   └── ai/              # Claude service (Phase 2)
│   └── alembic/             # migrations
└── web/                 # Vite + React + TS
    └── src/
        ├── App.tsx
        ├── lib/api.ts       # gọi backend
        └── pages/Dashboard.tsx
```

## Migrations (Alembic)

Khi thêm model (Phase 1), tạo & áp migration:

```bash
docker compose exec api alembic revision --autogenerate -m "add job & application"
docker compose exec api alembic upgrade head
```

## Roadmap

- **Phase 0** — Scaffold *(hiện tại)*
- **Phase 1** — Tracker MVP: job + pipeline Kanban (lọc part-time/hourly)
- **Phase 2** — CV/Proposal Studio + Claude AI
- **Phase 3** — Upwork API connector (poll saved-search)
- **Phase 4** — Scale-up (Freelancer.com, analytics)
