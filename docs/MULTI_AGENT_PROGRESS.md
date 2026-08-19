# Báo cáo tiến độ triển khai Multi-Agent

> Cập nhật: 2026-08-18
>
> Nhánh: `G19-T132-Lương-Trí-Tuệ`
>
> Trạng thái: hoàn thành cục bộ **Giai đoạn 0 — Foundation/Contract Baseline**; thay đổi chưa commit/merge lên remote.

## 1. Tóm tắt điều hành

Phần nền bắt buộc cho kiến trúc multi-agent theo workspace đã hoàn thành trong working tree. Hệ thống hiện đã có contract chung, mô hình Agent Workspace, membership, resource mapping, consent-aware authorization, resource guard và deterministic router skeleton.

Điều này chưa có nghĩa ba agent nghiệp vụ đã chạy hoàn chỉnh. Product Delivery Agent, Quality Assurance Agent và Executive Agent vẫn cần được xây dựng trên phần nền này. Router chưa được nối vào `/chat` để tránh đưa một luồng chưa đủ specialist tools và output validators vào người dùng hiện tại.

## 2. Tiến độ theo giai đoạn

| Giai đoạn | Trạng thái | Kết quả |
|---|---|---|
| PR-00 — Quality Assurance Rename | Hoàn thành cục bộ | Không còn identifier `customer_operations` trong runtime, migration hoặc test |
| PR-01 — Contracts & Flags | Hoàn thành cục bộ | Contract v1.0 và feature flag riêng cho từng profile |
| PR-02 — Workspace Scope | Hoàn thành cục bộ | Model, migration, API, membership, resource mapping và authorization baseline |
| Router Skeleton | Hoàn thành cục bộ | Profile registry, tool allowlist và deterministic routing |
| Product Delivery Agent | Chưa triển khai | Chờ vertical slice của owner Delivery |
| Quality Assurance Agent | Chưa triển khai | Chờ vertical slice của owner Quality |
| Executive Agent | Chưa triển khai | Có thể bắt đầu bằng WorkspaceBrief fixtures |
| Runtime `/chat` integration | Chưa triển khai | Chỉ nối sau khi profile, tool và output validator sẵn sàng |
| HITL executor hoàn chỉnh | Chưa triển khai | Hiện mới khóa `ActionProposal` contract |
| Agent Workspace UI | Chưa triển khai | Backend API đã sẵn sàng để UI sử dụng |

## 3. Những phần đã hoàn thành và giá trị mang lại

### 3.1 Chuẩn hóa Quality Assurance

Đã đổi toàn bộ profile cũ `customer_operations` thành `quality_assurance` trong enum, intent, feature flag, database constraint, migration và tests.

**Áp dụng**

- Delivery và Quality dùng đúng hai workspace nghiệp vụ đã thống nhất trong kế hoạch.
- Các thành viên không tạo prompt, migration hoặc dataset dựa trên hai tên khác nhau.

**Giá trị**

- Tránh sai profile khi ghép code.
- Giảm migration compatibility debt trước khi feature được phát hành.
- Giữ code, dataset và tài liệu cùng một ngôn ngữ nghiệp vụ.

### 3.2 Shared contracts version 1.0

Đã khóa các contract chung:

- `AgentContext`
- `SourceReference`
- `ToolResult`
- `ActionProposal`
- `WorkspaceBrief`
- `ExecutiveBrief`
- `PolicyDecision` và `PolicyReason`

Contract có strict schema, immutable server context, version, timestamp/freshness, source ownership và HITL payload-hash validation.

**Áp dụng**

- Delivery và Quality cùng tạo một dạng `WorkspaceBrief` chuẩn.
- Executive đọc brief có cấu trúc mà không cần đọc raw chat của phòng ban.
- Mỗi thành viên có thể phát triển agent riêng bằng fixture nhưng vẫn ghép được với shared core.

**Giá trị**

- Cho phép làm song song mà không tự tạo interface riêng.
- Bắt lỗi profile/source/freshness ngay tại schema boundary.
- Giảm hallucination không có nguồn và ngăn payload HITL bị sửa sau khi duyệt.

### 3.3 Agent Workspace model và migration

Đã có các bảng:

- `agent_workspaces`
- `agent_workspace_memberships`
- `agent_workspace_conversations`

Migration hỗ trợ cả upgrade và downgrade.

**Áp dụng**

- Một Organization Workspace có thể chứa Product Delivery Workspace và Quality Assurance Workspace.
- Thành viên được cấp business role riêng: `member`, `lead`, `executive_viewer`.
- Group conversation được gắn rõ vào đúng Agent Workspace.

**Giá trị**

- Tạo biên dữ liệu logic giữa các phòng ban mà không cần database vật lý riêng.
- Có cơ sở dữ liệu rõ ràng cho permission, routing và audit.
- Mở rộng thêm workspace/agent profile sau này mà không trộn dữ liệu cá nhân với dữ liệu phòng ban.

### 3.4 Agent Workspace Management API

Đã có API admin-only để:

- Tạo và liệt kê Agent Workspace.
- Gán hoặc thu hồi Agent Workspace membership.
- Gắn hoặc gỡ group conversation khỏi Agent Workspace.
- Ghi sanitized audit event cho thao tác cấu hình.

**Áp dụng**

- Workspace owner/admin cấu hình agent và membership.
- Admin chỉ có capability quản trị; không tự động có business entitlement để đọc dữ liệu nghiệp vụ.
- Backend đã sẵn sàng để xây trang quản trị Agent Workspace.

**Giá trị**

- Tách quyền cấu hình khỏi quyền sử dụng dữ liệu.
- Có thể truy vết ai đã cấp membership hoặc gắn resource.
- Giảm thao tác trực tiếp với database khi demo và vận hành.

### 3.5 Scope Resolver và resource-level authorization

Scope Resolver hiện kiểm tra:

```text
active user
∩ organization membership
∩ active Agent Workspace
∩ business membership
∩ agent profile
∩ requested scope
∩ target workspace
∩ mapped resource
∩ active group AI consent
```

**Áp dụng**

- Delivery member chỉ nhận resource IDs thuộc Delivery Workspace.
- Quality member không thể dùng guessed ID để đọc Delivery resource.
- Executive chỉ nhận danh sách workspace được cấp `executive_viewer`, không nhận raw resource IDs.
- Conversation chỉ vào agent scope khi đã được mapping và group AI consent đang bật.

**Giá trị**

- Chặn rò rỉ cross-workspace trước retrieval và model.
- Quyền được quyết định bằng trạng thái DB, không phải prompt hoặc lời LLM.
- Cho phép chứng minh nguyên tắc least privilege bằng automated tests.

### 3.6 Resource Guard tại tool boundary

Đã có guard để kiểm tra lại membership, consent scope hash và resource ID trước mỗi specialist tool call.

**Áp dụng**

- Membership bị revoke thì request/tool kế tiếp bị từ chối.
- Consent thay đổi sau khi context được tạo làm context cũ mất hiệu lực.
- Resource ID do model đoán không vượt qua allowlist hiện thời.

**Giá trị**

- Không phụ thuộc vào một lần kiểm tra quyền ở đầu request.
- Thu hồi quyền có hiệu lực ngay, hạn chế stale authorization.
- Tạo boundary chuẩn để mọi specialist tool dùng chung.

### 3.7 Deterministic registry/router skeleton

Đã có registry cho bốn profile:

- `personal`
- `product_delivery`
- `quality_assurance`
- `executive`

Mỗi profile có allowed scopes, allowed intents, prompt version và tool allowlist riêng. Router chọn profile từ requested scope, intent và Agent Workspace profile lấy từ DB; client không được tự gửi role/profile/allowlist.

**Áp dụng**

- Workspace Quality + `quality_brief` được route sang Quality Agent.
- Aggregate + `executive_brief` được route sang Executive Agent.
- Intent/profile mismatch hoặc workspace của organization khác bị từ chối.

**Giá trị**

- Routing có thể kiểm thử và tái lập, không phụ thuộc vào quyết định tùy ý của LLM.
- Một agent không thể gọi tool của agent khác.
- Có master/profile feature flags để rollout hoặc tắt an toàn.

### 3.8 Golden dataset 150 case

Đã có dataset multi-agent gồm 10 nhóm × 15 case:

- Delivery summary
- Quality readiness
- Executive aggregate
- Routing
- Workspace permission
- Prompt injection
- HITL
- Stale/partial brief
- Membership/consent revoke
- Cross-workspace dependency

**Áp dụng**

- Dùng làm fixture/acceptance contract cho các agent sắp triển khai.
- Dùng trong CI để phát hiện thay đổi làm sai routing, permission hoặc handoff logic.
- Bộ 17 case user-agent cũ vẫn được giữ làm compatibility regression baseline.

**Giá trị**

- Nhóm có tiêu chuẩn “done” chung thay vì đánh giá agent bằng cảm nhận.
- Có coverage cho cả happy path, denial, injection, stale data và revoke.
- Cho phép so sánh prompt/model/agent version về sau.

## 4. Luồng có thể áp dụng sau foundation

```text
Authenticated request
→ Resolve Organization Workspace
→ Deterministic Router chọn profile
→ Scope Resolver kiểm tra entitlement
→ Tạo immutable AgentContext
→ Chỉ cấp tool allowlist của profile
→ Resource Guard kiểm tra lại tại tool boundary
→ Specialist tạo validated WorkspaceBrief
→ Executive đọc brief được cấp quyền
→ Side effect tạo ActionProposal và chờ HITL
```

Hiện các bước từ request đến router/scope/context/guard đã có nền. Specialist execution, brief producer thật và HITL executor là phần tiếp theo.

## 5. Bằng chứng triển khai

| Thành phần | File chính |
|---|---|
| Kế hoạch và dependency | `docs/MULTI_AGENT_IMPLEMENTATION_PLAN.md` |
| Contract v1.0 | `src/agents/contracts.py` |
| Agent context builder | `src/agents/context_builder.py` |
| Scope resolver | `src/agents/policies/scope_resolver.py` |
| Tool-boundary resource guard | `src/agents/policies/resource_guard.py` |
| Profile/tool registry | `src/agents/tools/registry.py` |
| Deterministic router | `src/agents/router.py` |
| Agent Workspace API | `src/api/agent_workspace_routes.py` |
| API schemas | `src/models/agent_workspace_schemas.py` |
| Agent Workspace service | `src/services/agent_workspace_service.py` |
| Model và constraints | `src/db/models.py` |
| Migration | `src/db/migrations/versions/20260817_13_agent_workspaces.py` |
| Dataset | `eval/datasets/multi_agent_workspace_v1.jsonl` |
| Dataset generator/validator | `scripts/generate_multi_agent_dataset.py`, `scripts/validate_multi_agent_dataset.py` |

## 6. Kết quả kiểm thử gần nhất

| Gate | Kết quả |
|---|---:|
| Foundation contract/router/scope/migration tests | Pass |
| Security regression | 62/62 pass |
| Full backend regression | 281/281 pass |
| Golden dataset validation | 150/150 case hợp lệ |
| Ruff `src/tests/scripts` | Pass |
| Alembic upgrade/downgrade trên database tạm | Pass |
| User frontend production build | Pass |
| Admin frontend production build | Pass |

Các warning còn lại là deprecation từ Starlette/SQLite adapter và cảnh báo kích thước chunk frontend; không phải test failure của foundation.

## 7. Những gì chưa được tuyên bố là hoàn thành

- Chưa có Product Delivery Agent chạy trên tools/dữ liệu thật.
- Chưa có Quality Assurance Agent tính release readiness thật.
- Chưa có Executive Agent tổng hợp WorkspaceBrief thật.
- Chưa có WorkspaceBrief persistence/service và producer thật.
- Chưa nối multi-agent router vào `/chat`.
- Chưa có HITL executor, approval store và idempotent side-effect execution hoàn chỉnh.
- Chưa có Agent Workspace management UI.
- Dataset v1 hiện kiểm tra structural contract/policy; chưa phải điểm chất lượng LLM production.

## 8. Thứ tự công việc tiếp theo

1. Review, commit và merge Foundation/Contract Baseline.
2. Delivery owner xây Delivery schema, scoped read tools và brief producer.
3. Quality owner xây quality metadata, readiness rules, scoped read tools và brief producer.
4. Executive owner dùng Delivery/Quality brief fixtures để xây aggregate flow song song.
5. Nối brief producer thật vào Executive mà không mở raw-data access.
6. Hoàn thiện HITL executor, audit/runtime metrics và output validation.
7. Nối router vào `/chat` phía sau feature flags.
8. Chạy live-agent evaluation, staging demo và release gates.

## 9. Kết luận giá trị

Foundation hiện chưa tạo ra “ba chatbot mới” ngay lập tức; giá trị của nó là tạo một lõi chung để ba agent có thể được phát triển **song song, ghép được, kiểm thử được và không vượt quyền**.

Khi hoàn thiện các vertical slice tiếp theo, hệ thống có thể:

- Cho Delivery theo dõi milestone, blocker và dependency có nguồn.
- Cho Quality đánh giá release readiness từ bug/test facts có nguồn.
- Cho Executive nhận bức tranh tổng hợp mà không có quyền super-admin trên raw data.
- Thu hồi membership/consent có hiệu lực ngay.
- Mở rộng thêm workspace agent sau này bằng profile/contract/registry thay vì sao chép toàn bộ hệ thống.
