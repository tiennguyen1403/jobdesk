---
name: work-issue
description: Implement one GitHub issue for JobDesk end to end — read the issue, branch off development, code the change, run the checks, and open a PR into development. Run it per issue during daily work.
disable-model-invocation: true
---

# Work one issue

Issue to work: **#$ARGUMENTS**. If empty, list open issues (`gh issue list`) and ask which one.

Evidence-first: verify against the real code and by running things — don't claim, show output. Talk to the user in Vietnamese.

## Steps

1. **Read the issue.** `gh issue view $ARGUMENTS` — note the goal, the Definition of Done, the `area:*` label, and constraints. Read `CLAUDE.md` for architecture + the part-time scope.

2. **Branch off `development`.**
   ```bash
   git switch development && git pull
   git switch -c feat/$ARGUMENTS-<short-slug>
   ```

3. **Implement**, respecting the area:
   - `backend`/`db`: models in `app/models/` (+ register in `__init__.py`), migration via Alembic, routers under `/api`.
   - `frontend`: pages in `web/src/pages/`, data via `src/lib/api.ts`, Tailwind v4, dark UI.
   - `ai`: `app/ai/`; consult the `claude-api` skill for exact model/params.
   - `infra`: Docker/CI/config.
   Keep the part-time scope; new jobs map to `NormalizedJob`; never auto-apply/auto-message.

4. **Check locally** (paste the output):
   - Backend: `docker compose exec -T api sh -c "cd /app && ruff check . && python -m compileall app"`
   - Frontend: `docker compose exec -T web npm run build`
   - Migrations (if any): `docker compose exec api alembic upgrade head`
   - If endpoints changed: hit them and confirm the behavior.

5. **Commit & PR.**
   ```bash
   git add -A && git commit -m "<summary> (closes #$ARGUMENTS)"
   git push -u origin HEAD
   gh pr create --base development --fill --body "Closes #$ARGUMENTS"
   ```

6. **Report**: the PR URL + a one-line summary + the check output. CI + the reviewer are the gate; the PR auto-merges (squash) once green.
