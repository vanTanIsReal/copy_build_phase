# Role C — Ngày 1 run report

Ngày chạy: 2026-08-19  
Database: PostgreSQL 17, `qa_day1_20260819` (local test database)

## Kết quả

- `alembic upgrade head`: PASS, revision `20260819_15 (head)`.
- Chạy upgrade lần hai: PASS (idempotent).
- Các bảng `agent_workspaces` và `agent_workspace_memberships`: tồn tại.
- Partial unique index `uq_agent_workspace_active_lead`: tồn tại với điều kiện `business_role = 'lead' AND status = 'active'`.
- Constraints `ck_memory_type` và `ck_memory_sensitivity`: tồn tại đúng một lần trên PostgreSQL.
- Contract review: PASS với `WorkspaceBrief`, `SourceReference` (SourceRef), `ToolResult` data gaps/error semantics và `ActionProposal` HITL/expiry/hash.
- QA taxonomy đã chốt: test run, test case, defect, severity, regression, blocker, release candidate; critical/open hoặc thiếu evidence bắt buộc là `NOT_READY`/`BLOCKED` ở các ngày triển khai tool.

## Sửa trong Ngày 1

Migration `20260813_12_timeline_memory.py` đã được làm idempotent khi model-created tables đã có check constraints. Điều này khắc phục lỗi PostgreSQL `DuplicateObjectError: constraint "ck_memory_type" already exists` trên database mới.

## Phạm vi chưa thực hiện

Provision workspace và bật Role C chưa thực hiện trong Ngày 1; các bước đó thuộc Ngày 7 sau khi profile, service, tools, consent và E2E hoàn tất.
