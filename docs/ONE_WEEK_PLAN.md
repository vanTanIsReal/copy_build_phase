# Kế hoạch triển khai 7 ngày — 4 người (đã thay thế)

> **File này đã lỗi thời, không còn dùng để triển khai** (đánh dấu 2026-08-19).
>
> Bản kế hoạch dưới đây dùng khung phân cấp chức danh **Sếp/Trưởng phòng/Nhân viên**
> (Executive/Manager/Employee Agent, `business role: employee|manager|executive` map vào
> `department_ids`). Kế hoạch chính thức của nhóm đã đổi sang 3 agent theo **Agent Workspace
> nghiệp vụ** — Product Delivery / Quality Assurance / Executive — xem lý do đầy đủ tại
> [MULTI_AGENT_IMPLEMENTATION_PLAN.md](MULTI_AGENT_IMPLEMENTATION_PLAN.md) mục 1 "Tóm tắt quyết
> định".
>
> **Kế hoạch 7 ngày hiện hành** nằm tại
> [MULTI_AGENT_IMPLEMENTATION_PLAN.md §12 "Kế hoạch 7 ngày"](MULTI_AGENT_IMPLEMENTATION_PLAN.md#12-kế-hoạch-7-ngày)
> (Ngày 1–7: rename/contract freeze → core scope + 2 specialist read flow → WorkspaceBrief + UI
> skeleton → HITL + cross-workspace → security/eval → staging/demo rehearsal → freeze/evidence/demo).
> Phân công 4 người theo trục A/B/C/D (Platform, Delivery owner, Quality owner, Executive/Release
> owner) nằm ở [MULTI_AGENT_IMPLEMENTATION_PLAN.md §8](MULTI_AGENT_IMPLEMENTATION_PLAN.md#8-phân-công-nhóm-4-người)
> — khác cách chia A/B/C/D theo trục kỹ thuật (Orchestration/Policy/UX/Eval) ở bản cũ dưới đây.
>
> Tiến độ thật theo ngày: [MULTI_AGENT_PROGRESS.md](MULTI_AGENT_PROGRESS.md). Nội dung gốc của file
> này vẫn còn nguyên trong lịch sử git (`git log -- docs/ONE_WEEK_PLAN.md`) nếu cần đối chiếu quyết
> định đã đổi hướng ra sao — không nên copy lại phần chia vai trò/Git flow bên dưới vì đã bị thay thế.

---

## Bản gốc (lịch sử — không còn hiệu lực)

> Mục tiêu: có một vertical slice deploy online chứng minh ba role-agent, policy/HITL, proactive
> suggestion, UI theo role và benchmark. Không viết lại nền tảng hiện có.

Bản gốc chia 4 người theo trục kỹ thuật (A — Orchestration, B — Policy & data, C — User+admin UX,
D — Eval & release) và giả định 3 agent map theo chức danh Sếp/Trưởng phòng/Nhân viên. Toàn bộ nội
dung chi tiết (giả định/phạm vi, chia người, chiến lược Git, dependency, ngày cụ thể) đã được thay
bằng bản mới ở `MULTI_AGENT_IMPLEMENTATION_PLAN.md` (mục 8–12) — xem link ở trên thay vì đọc tiếp
phần này.
