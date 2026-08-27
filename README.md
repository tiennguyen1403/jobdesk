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

## What works today

- **Dashboard** — an analytics overview of your own data: source mix, pipeline funnel, match-score distribution, and AI spend.
- **Jobs** — add & browse postings, filtered to part-time / hourly / project work.
- **Sources** — connect Upwork & Freelancer (read-only OAuth) and manage the saved searches a background poller ingests from; jobs also arrive via manual add or the capture bookmarklet. Never auto-applies.
- **Pipeline** — a Kanban board tracking each application (saved → applied → interviewing → offer → rejected). Tracking-only; JobDesk never auto-applies.
- **Studio** (per job) — an AI match score, a tailored CV, and a proposal draft (Claude), edited in-app and copied out to apply manually on the platform.
- **AI cost logging** — every Claude call is recorded in the `ai_run` table for token/cost tracking.

## Quick start

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
│   │   ├── routers/         # health, jobs, applications, cvs, proposals, ai
│   │   ├── models/          # ORM models: job, application, cv, proposal, ai_run
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── providers/       # base.py (JobProvider + NormalizedJob), manual.py
│   │   └── ai/              # Claude service + ai_run cost logging (Phase 2)
│   └── alembic/             # migrations
└── web/                 # Vite + React + TS
    └── src/
        ├── App.tsx
        ├── lib/api/         # backend clients (jobs, applications, cvs, proposals)
        └── pages/           # Dashboard, Jobs, Pipeline, Studio
```

## Migrations (Alembic)

When you add a model, create & apply a migration:

```bash
docker compose exec api alembic revision --autogenerate -m "add job & application"
docker compose exec api alembic upgrade head
```

## Git & branches

- **`development`** = default/integration branch (all feature work).
- **`main`** = release/go-live only (`development` → `main` via PR).

## Roadmap

- **Phase 0** — Scaffold ✅
- **Phase 1** — Tracker MVP: Job + Application, list + part-time filter, Kanban ✅ *(v0.1.0)*
- **Phase 2** — CV/Proposal studio + Claude AI ✅ *(v0.2.0)*
- **Phase 3** — Upwork API connector (poll saved searches) ✅ *(v0.3.0)*
- **Phase 4** — Scale-up (Freelancer.com, analytics) ✅ *(v0.4.0)*
- **Phase 5** — Hardening & deploy (auth, token security, backup, hosting) ← next
