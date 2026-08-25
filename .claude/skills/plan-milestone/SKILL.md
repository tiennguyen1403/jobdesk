---
name: plan-milestone
description: Research a JobDesk milestone and turn it into GitHub issues. Reads CLAUDE.md + the blueprint + the code, produces a detailed plan, and creates one issue per task (with a Definition of Done and area label) under the milestone. Run at the start of each Phase.
disable-model-invocation: true
---

# Plan a milestone

Milestone to plan: **$ARGUMENTS** (e.g. `Phase 1 — Tracker MVP`). If empty, list milestones (`gh api repos/{owner}/{repo}/milestones --jq '.[].title'`) and ask which one.

Evidence-first: base the plan on the actual code and docs, not memory. Present findings and questions in Vietnamese to the user.

## Steps

1. **Research (ground truth).**
   - Read `CLAUDE.md`, `docs/multi-agent.md`, and the blueprint link inside `CLAUDE.md`.
   - Read the relevant existing code (`api/app/`, `web/src/`) so the plan fits what is really there.
   - Get the repo: `git remote get-url origin`. Confirm the milestone exists on GitHub.

2. **Decompose** the milestone into small, independent tasks. For each:
   - A verifiable **Definition of Done** (prefer "X works").
   - An **area**: `backend` | `frontend` | `db` | `ai` | `infra`.
   - Constraints to restate: part-time/hourly/project scope only; new jobs map to `NormalizedJob`; no auto-apply/auto-message.
   - Dependencies + whether it can run in parallel.

3. **Show the plan** to the user first (a short table: task, area, DoD, depends-on) and get a quick confirmation before creating issues.

4. **Create the issues** (one per task):
   ```bash
   gh issue create --title "<title>" --milestone "<milestone>" \
     --label "area:<x>,type:feat" \
     --body "$(printf '## Goal\n%s\n\n## Definition of Done\n- [ ] %s\n- [ ] CI green\n\n## Notes\nPart-time scope; new jobs map to NormalizedJob; no auto-apply.' "<goal>" "<dod>")"
   ```

5. **Report**: the created issue numbers + titles, the suggested order, and which can run in parallel. Tell the user they can now open a fresh session per issue and run `/work-issue <number>`.

Do **not** write feature code in this skill — planning + issue creation only.
