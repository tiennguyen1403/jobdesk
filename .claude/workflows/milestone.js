// @ts-nocheck — this is a Workflow DSL file (run by the Workflow tool, with the agent()/pipeline()/args
// globals and support for top-level await/return). It is NOT a normal TS module, so disable IDE type-checking here.
export const meta = {
  name: 'milestone',
  description: 'Run one JobDesk milestone: build tasks in parallel -> adversarial review -> overall QA -> report',
  phases: [
    { title: 'Build', detail: 'each specialist codes a task in its own worktree' },
    { title: 'Review', detail: 'reviewer inspects each change' },
    { title: 'QA', detail: 'qa runs docker + checks the Definition of Done' },
  ],
}

// args = { milestone: 'Phase 1', tasks: [{ area, title, spec }] }
// - area: 'backend' | 'frontend' | 'db' | 'ai' | 'infra'  (routes to an agent)
// - The coordinator usually produces this task list (with issue numbers) and passes it in.

const BUILD_SCHEMA = {
  type: 'object',
  required: ['summary', 'files', 'branch'],
  properties: {
    summary: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    branch: { type: 'string' },
    pr_url: { type: 'string' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'REQUEST_CHANGES'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string' },
          location: { type: 'string' },
          issue: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const QA_SCHEMA = {
  type: 'object',
  required: ['passed', 'checks'],
  properties: {
    passed: { type: 'boolean' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          status: { type: 'string' },
          evidence: { type: 'string' },
        },
      },
    },
  },
}

const AGENT_BY_AREA = {
  frontend: 'frontend-dev',
  backend: 'backend-dev',
  db: 'backend-dev',
  ai: 'ai-engineer',
  infra: 'devops',
}

const milestone = (args && args.milestone) || 'unnamed milestone'
const tasks = (args && args.tasks) || []

let output

if (!tasks.length) {
  output = {
    error: 'Pass args.tasks = [{ area, title, spec }]. Run the "coordinator" agent first to produce the list.',
  }
} else {
  // Build + Review as a pipeline: a task is reviewed as soon as it builds (no barrier).
  const results = await pipeline(
    tasks,
    (t) =>
      agent(
        `Task "${t.title}" for ${milestone}.\nSpec: ${t.spec}\n` +
          `Keep the part-time scope; new jobs must map to NormalizedJob; no auto-apply. ` +
          `Create a branch, code, commit (reference the issue), open a PR.`,
        {
          label: `build:${t.area}:${t.title}`,
          phase: 'Build',
          agentType: AGENT_BY_AREA[t.area] || 'backend-dev',
          isolation: 'worktree',
          schema: BUILD_SCHEMA,
        },
      ),
    (build, t) =>
      agent(
        `Adversarially review the change for task "${t.title}". Find bugs, scope errors, broken abstractions, missing DoD.\n` +
          `Build summary: ${JSON.stringify(build)}`,
        { label: `review:${t.title}`, phase: 'Review', agentType: 'reviewer', schema: REVIEW_SCHEMA },
      ).then((review) => ({ task: t, build, review })),
  )

  const clean = results.filter(Boolean)
  const changesRequested = clean.filter((r) => r.review && r.review.verdict === 'REQUEST_CHANGES')

  // Overall QA for the milestone (once, after tasks are built + reviewed).
  const qa = await agent(
    `You are QA. Run docker compose, check health + the new endpoints, run migrations/tests if any, ` +
      `and reconcile the Definition of Done for ${milestone}.\n` +
      `Tasks: ${JSON.stringify(clean.map((r) => r.task && r.task.title))}`,
    { label: 'qa:milestone', phase: 'QA', agentType: 'qa', schema: QA_SCHEMA },
  )

  output = {
    milestone,
    total: tasks.length,
    built: clean.length,
    changesRequested: changesRequested.map((r) => r.task && r.task.title),
    qaPassed: qa && qa.passed,
    results: clean,
    qa,
  }
}

return output
