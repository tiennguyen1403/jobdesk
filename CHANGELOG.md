# Changelog

All notable changes to JobDesk are documented here. Versions track the phase
roadmap (see the README); the format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed
- Backend: replaced the deprecated `HTTP_422_UNPROCESSABLE_ENTITY` status
  constant with `HTTP_422_UNPROCESSABLE_CONTENT` (Starlette 1.6 deprecation).
- Dev tooling: `ruff` is now a declared backend dependency, so
  `docker compose exec api ruff check .` runs locally exactly like CI.
- Docs: refreshed the README and CLAUDE.md to reflect Phases 1–2 as shipped.

## [0.2.0] — 2026-08-26 — Phase 2: CV/Proposal Studio + AI

### Added
- **AI foundation** — a Claude (Anthropic Messages API) client with every call
  logged to an `ai_run` table for token/cost tracking; `GET /api/ai/runs` and
  `POST /api/ai/smoke` (#34).
- **CV** data model + CRUD endpoints (`/api/cvs`) — base vs. job-tailored CVs (#35).
- **Proposal** data model + CRUD endpoints (`/api/proposals`) (#36).
- **`score_match`** — part-time fit scoring that weighs availability (workload /
  weekly hours / duration) above skill match; persists score/reasons on the job
  (`POST /api/jobs/{id}/score-match`) (#37).
- **`tailor_cv`** — job-tailored CV generation (`POST /api/jobs/{id}/tailor-cv`) (#38).
- **`draft_proposal`** — proposal drafting grounded in a CV
  (`POST /api/jobs/{id}/draft-proposal`) (#39).
- **CV/Proposal Studio** — a per-job screen (`/studio/:jobId`, reachable from a
  job card and a pipeline card) that shows the match score and generates + edits
  a tailored CV and a proposal draft, with a Copy button for manual apply (#40).

### Notes
- JobDesk never auto-applies: all three AI features produce drafts that the user
  reviews, edits, and submits manually on the platform.

## [0.1.0] — 2026-08-26 — Phase 1: Tracker MVP

### Added
- `Job` (a normalized posting) and its 1–1 `Application` (pipeline card) data
  models, with CRUD endpoints.
- Jobs list with the part-time / hourly / project-work scope filters.
- Kanban pipeline board (saved → applied → interviewing → offer → rejected) with
  drag-and-drop between stages and per-card notes.

## [0.0.0] — Phase 0: Scaffold

### Added
- Vite/React + FastAPI + PostgreSQL skeleton on Docker Compose.
- The provider layer (`JobProvider` / `NormalizedJob`) that keeps job ingestion
  source-agnostic, plus the health endpoint and CI.

[Unreleased]: https://github.com/tiennguyen1403/jobdesk/compare/v0.2.0...development
[0.2.0]: https://github.com/tiennguyen1403/jobdesk/releases/tag/v0.2.0
[0.1.0]: https://github.com/tiennguyen1403/jobdesk/releases/tag/v0.1.0
