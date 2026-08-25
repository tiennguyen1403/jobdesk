# JobDesk

A personal freelance job manager: aggregate jobs, track an application pipeline (Kanban), and build/tailor CVs & proposals per job. Upwork first; designed to add more platforms later.

> **Scope:** only **part-time / hourly / project-based** gigs (side work for evenings & weekends). Not full-time jobs.

📋 Detailed plan (architecture, data model, roadmap): see the **blueprint** — https://claude.ai/code/artifact/0bb986b5-66fd-495e-bed7-9d7dcc81cec5

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Vite + React + TypeScript, Tailwind v4, TanStack Query |
| Backend | FastAPI (Python), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 |
| Infra | Docker Compose |
| AI (Phase 2) | Claude API |

## Quick start (Phase 0 — skeleton)

```bash
# 1. Create the .env file from the template
cp .env.example .env        # PowerShell: Copy-Item .env.example .env

# 2. Start everything (db + api + web)
docker compose up --build
```

Once up (API host port from `API_PORT`, default `8000`; this machine uses `8001` because 8000 was taken):
- **Web:**  http://localhost:5173  — Dashboard shows API & DB connection status
- **API:**  http://localhost:8001  — auto docs at http://localhost:8001/docs
- **Health:** http://localhost:8001/api/health → `{"status":"ok","db":true}`

## Structure

```
job-management/
├── docker-compose.yml
├── .env.example
├── api/                 # FastAPI
│   ├── app/
│   │   ├── main.py          # app init + CORS + routers
│   │   ├── config.py        # settings (pydantic-settings)
│   │   ├── db.py            # SQLAlchemy engine/session/Base
│   │   ├── routers/         # health.py (+ jobs, applications... in Phase 1)
│   │   ├── models/          # ORM models (Phase 1)
│   │   ├── schemas/         # Pydantic schemas (Phase 1)
│   │   ├── providers/       # base.py: JobProvider + NormalizedJob
│   │   └── ai/              # Claude service (Phase 2)
│   └── alembic/             # migrations
└── web/                 # Vite + React + TS
    └── src/
        ├── App.tsx
        ├── lib/api.ts       # backend calls
        └── pages/Dashboard.tsx
```

## Migrations (Alembic)

When you add a model (Phase 1), create & apply a migration:

```bash
docker compose exec api alembic revision --autogenerate -m "add job & application"
docker compose exec api alembic upgrade head
```

## Git & branches

- **`development`** = default/integration branch (all feature work).
- **`main`** = release/go-live only (`development` → `main` via PR).

## Roadmap

- **Phase 0** — Scaffold *(current)*
- **Phase 1** — Tracker MVP: Job + Application, list + part-time filter, Kanban
- **Phase 2** — CV/Proposal studio + Claude AI
- **Phase 3** — Upwork API connector (poll saved searches)
- **Phase 4** — Scale-up (Freelancer.com, analytics)
