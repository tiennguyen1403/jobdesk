# Multi-agent operating model (semi-auto)

How JobDesk uses a team of agents that collaborate across milestones, coordinated by a **coordinator**, with a **human gate at each milestone boundary**.

## Principles

- **GitHub is the shared memory + work queue.** Milestone = Phase; Issue = task; PR = deliverable; CI = the objective judge.
- **Coordinator plans, specialists build, reviewer/QA gate.** No agent "runs the whole project" on its own.
- **Semi-auto:** agents run a full milestone (create issues → code → review → PR); **you review & approve the PRs at the milestone boundary**.

## Roles (defined in `.claude/agents/`)

| Agent | Job |
|---|---|
| `coordinator` | Break a milestone into issues with a DoD + `area:*` labels; propose order & parallelism. No code. |
| `backend-dev` | `area:backend`/`db`: FastAPI/SQLAlchemy/Alembic → branch → PR. |
| `frontend-dev` | `area:frontend`: React/Vite/Tailwind v4 → branch → PR. |
| `ai-engineer` | `area:ai`: Claude integration (tailor/draft/score), prompts, structured output, cost. |
| `devops` | `area:infra`: Docker, CI, repo/branch config, secrets, deploy. |
| `reviewer` | Adversarial review (correctness, part-time scope, Provider layer). Verdict APPROVE / REQUEST_CHANGES. |
| `qa` | Run docker, check health/endpoints/migrations/tests, verify the DoD. |

## Flow for one milestone

```
1. coordinator: read the milestone → create issues (gh) with milestone + area labels
2. Workflow "milestone": [backend-dev ∥ frontend-dev ∥ ...] each task in its own worktree/branch → PR
                         → reviewer checks each PR → qa runs the whole thing
3. Gate: CI green + reviewer APPROVE → auto-merge (squash)
4. You (human): review the integrated result at the milestone boundary → approve or request changes
```

## How to run

- **Plan:** run `/plan-milestone "Phase 1 — Tracker MVP"` (or spawn the `coordinator` agent). It researches and creates the issues.
- **Work one issue:** run `/work-issue <number>` — reads the issue, branches off `development`, implements, and opens a PR.
- **Deterministic execution:** run the `Workflow` template `milestone` with
  `args = { milestone: "Phase 1", tasks: [{ area, title, spec }] }` (the coordinator produces this list).

## Branches

- Feature branch `feat/<issue>-<slug>` off **`development`** → PR into **`development`**.
- **`main`** is release-only: `development` → `main` at go-live.
- Both branches are protected (PR + green CI). Merge = squash, branch auto-deleted.

## Guardrails

- **Worktree isolation** when multiple agents edit files in parallel → no clobbering.
- **Review + CI are required gates** (branch protection) before merge.
- **Small issues, clear DoD** — agents do best with narrow tasks.
- **Shared ground truth:** `CLAUDE.md` + blueprint + a per-milestone spec.

> Reality: fully autonomous multi-agent dev is still error-prone. The value is parallel specialist execution + independent review/verification + structured milestone tracking — **with a human gate at each milestone**.
