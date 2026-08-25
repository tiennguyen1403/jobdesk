// @ts-nocheck — file này là Workflow DSL (chạy bởi tool Workflow với các global agent()/pipeline()/args
// và hỗ trợ top-level await/return). KHÔNG phải TS module thường, nên tắt type-check của IDE ở đây.
export const meta = {
  name: 'milestone',
  description: 'Chạy 1 milestone JobDesk: build song song theo task → review đối kháng → QA tổng thể → báo cáo',
  phases: [
    { title: 'Build', detail: 'specialist code từng task trong worktree riêng' },
    { title: 'Review', detail: 'reviewer soi từng thay đổi' },
    { title: 'QA', detail: 'qa chạy docker + đối chiếu Definition of Done' },
  ],
}

// args = { milestone: 'Phase 1', tasks: [{ area, title, spec }] }
// - area: 'backend' | 'frontend' | 'db' | 'ai' | 'infra'  (route tới agent)
// - Coordinator thường sinh danh sách tasks này (kèm số issue) rồi truyền vào đây.

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
    error: 'Truyền args.tasks = [{ area, title, spec }]. Chạy agent "coordinator" trước để sinh danh sách.',
  }
} else {
  // Build ∥ Review theo pipeline: task nào build xong thì review ngay (không chờ nhau).
  const results = await pipeline(
    tasks,
    (t) =>
      agent(
        `Task "${t.title}" cho ${milestone}.\nSpec: ${t.spec}\n` +
          `Giữ scope part-time; job mới map về NormalizedJob; không auto-apply. ` +
          `Tạo branch, code, commit (gắn số issue), mở PR.`,
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
        `Review đối kháng thay đổi cho task "${t.title}". Tìm bug, sai scope, phá abstraction, thiếu DoD.\n` +
          `Tóm tắt build: ${JSON.stringify(build)}`,
        { label: `review:${t.title}`, phase: 'Review', agentType: 'reviewer', schema: REVIEW_SCHEMA },
      ).then((review) => ({ task: t, build, review })),
  )

  const clean = results.filter(Boolean)
  const changesRequested = clean.filter((r) => r.review && r.review.verdict === 'REQUEST_CHANGES')

  // QA tổng thể milestone (một lần, sau khi các task đã build + review).
  const qa = await agent(
    `Bạn là QA. Chạy docker compose, kiểm health + endpoint mới, chạy migration/test nếu có, ` +
      `đối chiếu Definition of Done của ${milestone}.\n` +
      `Các task: ${JSON.stringify(clean.map((r) => r.task && r.task.title))}`,
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
