# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

JobDesk — a personal, local-first freelance job manager: aggregate jobs, track an application pipeline (Kanban), and build/tailor CVs + proposals per job. Upwork first; designed to add more platforms later.

**Scope constraint that shapes every feature:** only **part-time / hourly / project-based** gigs (side work for evenings & weekends) — never full-time. `NormalizedJob` carries `workload` / `weekly_hours` / `duration`; job filtering and AI match-scoring must weigh availability.

**Platform reality that drives the architecture:** the Upwork API can *read/search* jobs but has **no mutation to submit a proposal** — applying is always done manually on Upwork; this app tracks and assists, it never auto-applies. API access needs manual approval and has no webhooks (poll only). Because approval is uncertain, job ingestion is deliberately provider-agnostic so the app is fully useful with manual entry alone.

## Run (Docker is the primary workflow)

Everything runs via Docker Compose; the compose project name is pinned to `jobdesk` (independent of the folder name).

- `docker compose up -d --build` — start db + api + web
- `docker compose down` — stop (add `-v` to also wipe the Postgres volume)
- `docker compose logs -f api` — tail logs (`web` / `db` too)

First run only: `cp .env.example .env`.

URLs (host ports come from `.env`): web at http://localhost:5173 · API at `http://localhost:$API_PORT` (interactive docs at `/docs`, health at `/api/health`). **`API_PORT` defaults to `8000`, but this machine uses `8001`** because another Docker service holds 8000 — keep `API_PORT` and `VITE_API_BASE` in `.env` in sync when changing it.

### Database migrations (Alembic — run inside the api container)

- `docker compose exec api alembic revision --autogenerate -m "message"`
- `docker compose exec api alembic upgrade head`

Autogenerate only detects models that are imported in `api/app/models/__init__.py` — register every new model module there or migrations will miss it.

### Other in-container commands

- `docker compose exec web npm run build` — frontend typecheck + production build
- `docker compose exec api python -m compileall app` — quick backend syntax check

No automated test suite exists yet (planned Phase 1+): add `pytest` under `api/` and Vitest under `web/` when tests arrive.

## Architecture (big picture)

Three tiers — **Vite/React SPA → FastAPI → PostgreSQL** — plus two cross-cutting backend layers:

- **Provider layer** (`api/app/providers/`) — the central abstraction. Every job source implements `JobProvider.fetch() -> list[NormalizedJob]` (`base.py`). `NormalizedJob` is the one normalized shape the rest of the app consumes, so the pipeline / CV / AI / UI never depend on where a job came from. Adding a platform = one new provider class, nothing else changes. Planned providers: `manual`, `capture` (bookmarklet → `POST /api/capture`), `upwork` (GraphQL, polled by APScheduler once approved).
- **AI layer** (`api/app/ai/`, Phase 2) — Claude via the Anthropic Messages API for `tailor_cv`, `draft_proposal`, `score_match`. Every call is logged to an `ai_run` table for token/cost tracking; `score_match` weighs part-time/evening fit.

Config is centralized in `api/app/config.py` (pydantic-settings, env-driven). The SQLAlchemy engine/session and declarative `Base` live in `api/app/db.py`. Routers under `api/app/routers/` are mounted under the `/api` prefix in `main.py`.

Core data model (Phase 1+): `job` (a normalized posting) 1–1 `application` (the pipeline card linking a job to the cv/proposal used to apply). Full schema in the blueprint linked below.

## Conventions

- **Language:** all repository content — docs, code, comments, commit messages, PRs — is in **English**. (Vietnamese is used only when chatting with the maintainer, never in the repo.)
- **Tailwind v4 (CSS-first):** styling is enabled by `@import "tailwindcss";` in `web/src/index.css` via the `@tailwindcss/vite` plugin. There is intentionally **no** `tailwind.config.js` or PostCSS config — customize through a `@theme {}` block in that CSS file. The web UI is **dark by default** (slate-950).

## Daily workflow (skills)

- `/plan-milestone "Phase N — ..."` — research a milestone and create its GitHub issues (one per task, each with a DoD + `area:*` label). Run at the start of a Phase.
- `/work-issue <number>` — implement one issue end to end: branch off `development`, code, run checks, open a PR. One issue per session.

Project hooks in `.claude/settings.json`: ask before editing `.env` (secrets); warn when committing on `main`.

## Git & branches

- **`development`** is the default/integration branch — feature work branches off it and PRs back into it.
- **`main`** is release/go-live only; ship via a `development` → `main` PR.
- Both branches are protected: PR + green CI (`backend`, `frontend`) required; repo owner (admin) can bypass. Merge = squash, branch auto-deleted.
- Feature branches: `feat/<issue>-<slug>`; reference the issue in commits and the PR.

## Roadmap

Phase 0 scaffold (done) → Phase 1 tracker MVP (job + application, list + part-time filter, Kanban) **(done, v0.1.0)** → Phase 2 CV/proposal studio + Claude AI **(done, v0.2.0)** → Phase 3 Upwork API connector **(done, v0.3.0)** → Phase 4 scale-up (Freelancer.com, analytics) **(done, v0.4.0)** → **Phase 5 hardening & deploy (auth, token security, backup, hosting) (next)**.

Full blueprint (architecture, data model, API endpoints, roadmap): https://claude.ai/code/artifact/0bb986b5-66fd-495e-bed7-9d7dcc81cec5
