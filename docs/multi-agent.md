# Mô hình vận hành multi-agent (semi-auto)

Cách JobDesk dùng một nhóm agent phối hợp qua các milestone, với **coordinator** điều phối và **người gác cổng ở ranh giới milestone**.

## Nguyên tắc

- **GitHub là bộ nhớ chung + hàng đợi việc.** Milestone = Phase; Issue = task; PR = deliverable; CI = trọng tài khách quan.
- **Coordinator lập kế hoạch, specialist thực thi, reviewer/QA làm cổng.** Không agent nào "tự chạy cả project".
- **Semi-auto:** agent chạy trọn một milestone (tạo issue → code → review → PR); **bạn review & duyệt PR ở ranh giới milestone**.

## Vai trò (định nghĩa ở `.claude/agents/`)

| Agent | Việc |
|---|---|
| `coordinator` | Bẻ milestone → issue có DoD + label `area:*`; đề xuất thứ tự & việc song song. Không code. |
| `backend-dev` | Task `area:backend`/`db`: FastAPI/SQLAlchemy/Alembic → branch → PR. |
| `frontend-dev` | Task `area:frontend`: React/Vite/Tailwind v4 → branch → PR. |
| `reviewer` | Review đối kháng (correctness, scope part-time, tầng Provider). Verdict APPROVE / REQUEST_CHANGES. |
| `qa` | Chạy docker, health/endpoint/migration/test, đối chiếu DoD. |

## Luồng một milestone

```
1. coordinator: đọc milestone → tạo issues (gh) gắn milestone + label area
2. Workflow "milestone": [backend-dev ∥ frontend-dev] mỗi task 1 worktree/branch → PR
                         → reviewer soi từng PR → qa chạy tổng thể
3. Cổng: CI xanh + reviewer APPROVE → auto-merge (squash)
4. Bạn (human): review kết quả tích hợp ở cuối milestone → duyệt hoặc yêu cầu sửa
```

## Cách chạy

- **Lập kế hoạch:** spawn agent `coordinator` với mục tiêu milestone (vd "Phase 1 — Tracker MVP"). Nó tạo issue.
- **Thực thi xác định:** chạy `Workflow` template `milestone` với
  `args = { milestone: "Phase 1", tasks: [{ area, title, spec }] }` (coordinator sinh danh sách này).
- **Thực thi linh hoạt:** hoặc để session chính spawn từng specialist qua tool `Agent` cho các task rời rạc.

## Guardrails

- **Worktree isolation** khi nhiều agent sửa file song song → không giẫm chân nhau.
- **Review + CI là cổng bắt buộc** (branch protection trên `main`) trước khi merge.
- **Issue nhỏ, DoD rõ** — agent làm tốt khi task hẹp.
- **Ground truth chung:** `CLAUDE.md` + blueprint + spec từng milestone.

> Thực tế: multi-agent tự chủ hoàn toàn vẫn dễ lỗi. Giá trị nằm ở chạy song song specialist + review/verify độc lập + theo dõi milestone có cấu trúc — **với người gác cổng ở mỗi milestone**.
