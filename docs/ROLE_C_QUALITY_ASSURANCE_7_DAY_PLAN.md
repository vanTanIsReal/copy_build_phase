# Role C — Quality Assurance Workspace và kế hoạch hoàn thiện 7 ngày

Ngày lập: 2026-08-19  
Phạm vi: Quality Assurance Agent (Role C), Workspace doanh nghiệp một công ty

## 1. Kết luận rà soát Workspace

### Đã phù hợp với mô hình doanh nghiệp

- Company Root được thiết kế singleton (`slug=company-root`), người dùng không tự tạo hoặc chuyển tenant.
- Workspace phòng ban tách khỏi Personal Workspace; quyền nghiệp vụ nằm ở membership theo từng Agent Workspace.
- Control plane tạo/sửa workspace, gán lead/member và liên kết conversation chỉ dành cho Platform Admin.
- Scope resolver kiểm tra account active, Company membership, workspace active, agent profile, business role, resource ID và consent trước retrieval; thiếu điều kiện thì `DENY`.
- Executive chỉ nhận aggregate/validated brief từ Delivery và QA, không được đọc raw chat, memory, calendar hoặc file riêng.
- Có lifecycle active/suspended/archived, revoke membership có hiệu lực ở request kế tiếp, audit event và support grant có phê duyệt.
- Bộ test hiện có đã bao phủ nhiều negative case: cross-workspace, sai profile, revoke membership, consent thay đổi và executive scope.

### Chưa đạt mức sẵn sàng enterprise để bật Role C

1. Database local chưa đồng bộ với code: `alembic current` dừng tại revision không còn trong repository (`20260812_07`), bảng `agent_workspaces` chưa tồn tại. Không được provision workspace vào DB này trước khi xử lý migration chain.
2. Quality Agent runtime chưa có vertical slice thật: chưa có profile, quality tools/service/schema/UI theo ownership đã nêu trong `MULTI_AGENT_IMPLEMENTATION_PLAN.md`.
3. `POST /api/v1/workspaces` vẫn tồn tại cho tương thích demo và chỉ bị chặn bằng config. Production phải giữ `ALLOW_SELF_SERVICE_ORGANIZATION_CREATION=false` và cần acceptance test kiểm tra drift cấu hình.
4. Cần E2E từ Admin provision → user discovery → QA brief → executive aggregate, cùng bằng chứng không rò rỉ Delivery raw data và HITL cho side effect.

**Đánh giá:** kiến trúc authorization là nền tảng phù hợp, nhưng chưa nên bật Role C trên môi trường doanh nghiệp cho tới khi hoàn tất migration và 7 ngày hardening dưới đây.

## 2. Workspace cần provision cho Role C

Đây là một Agent Workspace thuộc Company Root, không phải một Company/tenant mới.

| Trường | Giá trị chuẩn |
|---|---|
| `key` | `quality-assurance` |
| `name` | `Quality Assurance Workspace` |
| `agent_profile` | `quality_assurance` |
| `status` | `active` sau khi migration và smoke test pass |
| Lead | Một active non-platform user do Platform Admin chọn |
| Member role | `member`; lead giữ đúng một membership `lead` |
| Data boundary | QA work items, test/bug/release facts và group conversations đã consent |
| Không được đọc | Delivery raw chat, private memory/calendar/file và resource ngoài QA scope |

Provision chính thức chỉ thực hiện sau khi database ở migration head:

```http
POST /api/v1/workspaces/{company_root_id}/agent-workspaces
Authorization: Bearer <platform-admin-token>
Content-Type: application/json

{
  "key": "quality-assurance",
  "name": "Quality Assurance Workspace",
  "agent_profile": "quality_assurance",
  "lead_email": "<active-qa-lead-email>"
}
```

Không hard-code email lead trong migration hoặc fixture production. Sau khi tạo, Admin thêm member qua endpoint members và kiểm tra `GET .../available` bằng tài khoản lead/member.

## 3. Kế hoạch Role C trong 7 ngày

### Ngày 1 — Khóa nền tảng và dữ liệu đầu vào

- Sửa/đồng bộ migration chain, chạy preflight và upgrade một database test riêng lên head.
- Xác nhận Company Root singleton, active membership và partial unique active lead.
- Chốt contract `WorkspaceBrief`, `QualityBrief`, `SourceRef`, freshness/data-gap và proposal/HITL với owner shared contracts.
- Chốt taxonomy QA: test run, test case, defect, severity, regression, blocker, release candidate.

**Hoàn thành khi:** DB test ở head; migration/negative workspace tests pass; contract review được ghi nhận.

**Trạng thái Ngày 1 (2026-08-19):** PASS trên PostgreSQL 17; xem [run report](ROLE_C_DAY1_RUN_REPORT.md).

### Ngày 2 — Quality profile và scoped services

- Tạo `src/agents/profiles/quality_assurance.py` với intent, system prompt, allowed tools và output limits.
- Tạo `src/agents/schemas/quality.py` cho facts, readiness decision, source/freshness và explicit data gaps.
- Tạo `src/services/quality_workspace_service.py` với query chỉ nhận `organization_workspace_id`, `agent_workspace_id` từ server-resolved context.
- Không nhận workspace/member/allowed-resource IDs do client tự khai báo.

**Hoàn thành khi:** profile đăng ký được qua registry; unit test chứng minh sai profile/sai workspace bị deny.

### Ngày 3 — QA tools và release-readiness rules

- Implement `quality_*.py` tools: test progress, defect summary, regression status, release readiness và source lookup.
- Khóa rule: bất kỳ critical defect đang mở hoặc thiếu evidence bắt buộc ⇒ `NOT_READY`/`BLOCKED`.
- Mọi tool result có source ID, timestamp, freshness, confidence và data gaps.
- Side effect (assign bug, tạo meeting, đổi trạng thái) chỉ trả proposal chờ HITL.

**Hoàn thành khi:** critical bug luôn làm release `NOT_READY`; không có tool nào gọi raw Delivery resource.

### Ngày 4 — Tích hợp agent runtime và consent

- Nối QA profile vào router/graph/context builder bằng interface hiện có, không sửa shared contract ngoài PR riêng.
- Áp dụng conversation classification `quality` và AI consent trước khi lấy message resource.
- Kiểm tra retention, audit metadata và prompt version; không log raw message/secret.
- Seed một QA workspace test với lead/member và dữ liệu synthetic đã validate.

**Hoàn thành khi:** happy path tạo được `QualityBrief` thật từ dữ liệu có consent; revoke consent làm request kế tiếp fail closed.

### Ngày 5 — UI và vận hành Workspace

- Xây Quality page/cards: readiness, test pass rate, open defects, blockers, freshness, source links và data gaps.
- Hiển thị rõ `DENY`, `NOT_READY`, `STALE`, `PARTIAL` và lỗi cấu hình; không che bằng số liệu mặc định.
- Nối Workspace selector với `available` endpoint; không cho user/member gọi control-plane API.
- Bổ sung audit timeline cho create/update/lead/member/conversation link.

**Hoàn thành khi:** lead/member chỉ thấy QA Workspace được cấp; Delivery member không thấy QA resource.

### Ngày 6 — Test bảo mật, E2E và hiệu năng

- Unit/integration tests cho profile, validator, service, readiness và proposals.
- Security matrix: wrong workspace, wrong profile, suspended workspace, revoked membership, missing consent, stale/partial data, platform admin không có raw-data entitlement.
- E2E: Admin tạo QA → gán lead/member → user discovery → QA brief → proposal/HITL.
- Đo query count/latency, pagination và timeout; thêm structured logs với trace ID.

**Hoàn thành khi:** leakage = 0, mọi side effect có HITL = 100%, regression suite pass.

### Ngày 7 — Provision, release gate và bàn giao

- Chạy migration head trên staging snapshot; backup/rollback plan được duyệt.
- Provision `quality-assurance` Workspace bằng Platform Admin, xác minh đúng một active lead và membership.
- Chạy smoke/E2E và kiểm tra executive aggregate chỉ dùng validated QA brief.
- Bật `QUALITY_ASSURANCE_AGENT_ENABLED` theo staged rollout, theo dõi deny/error/latency/token metrics.
- Bàn giao runbook, fixture manifest, test report, known limitations và kế hoạch rollback.

**Hoàn thành khi:** Role C đạt sign-off của owner policy, Delivery reviewer và Release owner; không còn blocker migration hoặc security.

## 4. Definition of Done cho Role C

- [ ] Database migration head hợp lệ trên môi trường đích.
- [ ] `quality_assurance` profile, tools, schema, service và UI chạy qua registry hiện tại.
- [ ] QualityBrief validate được và có source/freshness/data-gap.
- [ ] Critical defect mở luôn trả `NOT_READY`.
- [ ] Cross-workspace/raw Delivery access bị deny trước retrieval.
- [ ] Consent revoke, membership revoke, suspend workspace có hiệu lực ngay request kế tiếp.
- [ ] Mọi side effect là proposal và cần HITL.
- [ ] Admin provision QA Workspace thành công; đúng một active lead.
- [ ] Unit, integration, security và E2E pass; leakage = 0.
- [ ] Executive aggregate đọc được QA brief thật mà không cần raw chat.
