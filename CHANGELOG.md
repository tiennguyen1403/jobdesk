# Changelog

All notable changes to JobDesk are documented here. Versions track the phase
roadmap (see the README); the format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.3.0] — 2026-08-27 — Phase 3: Upwork API connector

### Added
- **Provider-agnostic ingestion** — one `ingest_jobs()` upsert/dedupe spine keyed
  on `(source, external_id)` that every source writes through; ingested jobs land
  in the Inbox and never auto-open a pipeline card (#52).
- **Browser-capture provider** — `POST /api/capture` + a documented bookmarklet
  (`docs/capture-bookmarklet.md`) that scrapes the Upwork job you're viewing and
  ingests it, so the app is useful before any API approval (#53).
- **Upwork OAuth2 connect flow** — `GET /api/upwork/connect|callback|status` and
  `POST /api/upwork/disconnect`; tokens are stored locally with a refresh helper,
  the endpoints return a clean `503` when `UPWORK_CLIENT_ID` / `UPWORK_CLIENT_SECRET`
  are unset, and the callback redirects back to the SPA `/sources` (#54, #69).
- **Upwork GraphQL provider** — runs `marketplaceJobPostingsSearch` and maps each
  posting to `NormalizedJob` (including the part-time signals workload /
  weekly_hours / duration), refreshing and retrying once on a 401 (#55).
- **Saved searches** — a `saved_search` model + `/api/saved-searches` CRUD whose
  `query` JSONB carries first-class part-time constraints (workload /
  max_weekly_hours) (#56).
- **Polling scheduler** — an in-process APScheduler loop (env-gated by
  `POLL_ENABLED`, safe under `--reload`) that polls enabled saved searches, plus
  `POST /api/saved-searches/{id}/run` to run one immediately (#57).
- **Sources page** — connect / disconnect Upwork, manage saved searches, and run a
  poll with its ingest result, plus a connect-result banner after the OAuth
  redirect (#58, #71).
- **Ingested-job surfacing** — a source badge (manual / capture / upwork) and a
  source filter on the Jobs list, plus an "Add to pipeline" promote action (#59).
- **AI Runs view** — a `/ai-runs` screen over the `ai_run` cost/usage ledger
  (Phase 2 polish) (#49).

### Fixed
- **Part-time scope on the poll** — the poll now drops full-time postings and
  honors a saved search's `max_weekly_hours` before ingest; the saved-search
  workload is constrained to `part_time` (a `full_time` search is a 422), the
  Sources form drops the Full-time option, and `category` is folded into the
  Upwork search expression instead of being ignored (#73).
- **`score_match` structured output** — dropped the JSON-schema value-constraint
  keywords the Anthropic API rejects; the bounds now live in the prompt and a code
  clamp (#51).

### Changed
- Backend: replaced the deprecated `HTTP_422_UNPROCESSABLE_ENTITY` status
  constant with `HTTP_422_UNPROCESSABLE_CONTENT` (Starlette 1.6 deprecation).
- Dev tooling: `ruff` is now a declared backend dependency, so
  `docker compose exec api ruff check .` runs locally exactly like CI.
- Docs: refreshed the README and CLAUDE.md to reflect Phases 1–2 as shipped.

### Notes
- JobDesk still never auto-applies: the Upwork API is read/search only (no
  submit-proposal mutation) — the connector ingests and tracks jobs, nothing more.

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

[Unreleased]: https://github.com/tiennguyen1403/jobdesk/compare/v0.3.0...development
[0.3.0]: https://github.com/tiennguyen1403/jobdesk/releases/tag/v0.3.0
[0.2.0]: https://github.com/tiennguyen1403/jobdesk/releases/tag/v0.2.0
[0.1.0]: https://github.com/tiennguyen1403/jobdesk/releases/tag/v0.1.0
