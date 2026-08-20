# Kế hoạch và báo cáo thực hiện 7 ngày — Người C: Quality Assurance Agent

> **Owner:** C — Quality Assurance Agent Owner
>
> **Thời lượng:** 7 ngày làm việc
>
> **Mục tiêu:** hoàn thành một Quality Assurance vertical slice từ scoped data → tools → Agent → Quality WorkspaceBrief → UI → HITL → eval, không vượt ranh giới Quality Assurance Workspace.
>
> **Foundation:** Quality Assurance Workspace phải có trước khi bắt đầu; xem [Enterprise Workspace Foundation](ENTERPRISE_WORKSPACE_FOUNDATION.md).
>
> **Quy ước báo cáo:** đây là file báo cáo duy nhất của Role C. Sau mỗi ngày, cập nhật trạng thái, kết quả, test và evidence trực tiếp vào mục 6; không tạo thêm file `ROLE_C_DAY*.md` hoặc `QUALITY_ASSURANCE_DAY*.md`.

## 1. Kết quả cuối tuần

Người C phải bàn giao được một Quality Assurance Agent có thể:

1. Nhận request `quality_readiness` hoặc `quality_brief` từ lead/member hợp lệ trong Workspace `quality-assurance`.
2. Chỉ đọc bug, test case, release check và QA conversation đã link, còn hiệu lực consent.
3. Tổng hợp test progress, defect, failed/blocked test, regression và release check.
4. Tính `READY | AT_RISK | NOT_READY` bằng rule trong code; model không được tự đổi kết quả.
5. Phân biệt fact, inference, recommendation và data gap; mọi finding quan trọng đều có source.
6. Sinh `WorkspaceBrief(brief_type=quality)` đúng contract v1 để Delivery và Executive sử dụng.
7. Tạo reminder, meeting, bug assignment hoặc bug status update dưới dạng proposal chờ HITL; không tự thực thi.
8. Hiển thị loading, empty, denied, partial, stale và error state trên User UI.
9. Vượt qua golden dataset, cross-workspace denial, consent revoke, prompt-injection và HITL tests.

Không coi Agent hoàn thành nếu chỉ có prompt, chỉ chạy bằng mock hoặc tính readiness bằng suy luận tự do của model.

## 2. Baseline trước ngày 1

### 2.1 Đã có

- Company Root single-company và Quality Assurance Workspace key canonical `quality-assurance`.
- Lead/member lifecycle, user discovery, scope resolver, resource guard và conversation mapping `classification=quality`.
- `AgentContext`, `AgentState`, router, profile registry và feature flag `QUALITY_ASSURANCE_AGENT_ENABLED`, mặc định tắt.
- Common contract `ToolResult`, `SourceReference`, `ActionProposal` và `WorkspaceBrief` v1.
- `QualityWorkItem`, `QualityReadinessAssessment` và rule `evaluate_release_readiness` trong code.
- Profile/prompt skeleton `quality_assurance-v1`.
- 15 case `quality_readiness`: 5 `READY`, 5 `AT_RISK`, 5 `NOT_READY`.
- Báo cáo Ngày 1 đã pass trên PostgreSQL 17; evidence được ghi trực tiếp tại mục 6 của tài liệu này.

### 2.2 Chưa có và phải xử lý trong tuần

- Quality scoped service và tool implementations dùng dữ liệu thật.
- Tool allowlist rút gọn và adapter chuyển từ tên tool cũ.
- Agent invocation path chạy profile QA qua runtime thật.
- Quality WorkspaceBrief producer/store integration.
- Quality UI và source/freshness states.
- Durable HITL integration cho proposal QA.
- Live evaluator, E2E và release evidence.

### 2.3 Dependency phải khóa với A, B và D

| Dependency | Owner | C được làm trước bằng gì | Điều kiện nối thật |
|---|---|---|---|
| Invocation API/profile runner | A | Gọi profile handler trực tiếp trong test | Router và context builder chạy trước model |
| Scoped work-item query | A | Fixture có `allowed_resource_ids` | Query policy có negative test và không fallback Company-wide |
| WorkspaceBrief persistence | A + D | Validate và trả object in-memory | Store có lineage, expiry và audit |
| Structured release/dependency reference | B | Fixture theo common contract | B cung cấp reference/brief, không truyền raw Delivery chat |
| Durable ActionProposal executor | A | Tạo proposal object, dùng fake executor | Revalidation, expiry và idempotency tests xanh |
| Executive brief consumer | D | Contract fixture | D đọc được Quality brief mà không parse text tự do |
| Shared Workspace UI shell | A | Component QA độc lập bằng fixture | Workspace context/capability API ổn định |

Nếu scoped work-item query chưa có, C không được query toàn Company. Chỉ dùng fixture hoặc record chứng minh được nguồn từ `allowed_resource_ids`.

## 3. Phạm vi sở hữu

### 3.1 C được tạo và sửa

```text
src/agents/profiles/quality_assurance.py
src/agents/schemas/quality.py
src/agents/tools/quality_snapshot.py
src/agents/tools/quality_evidence.py
src/agents/tools/quality_brief.py
src/agents/tools/quality_actions.py
src/services/quality_workspace_service.py
Frontend/user/src/components/agents/quality/*
Frontend/user/src/pages/QualityAgentPage.jsx
eval/fixtures/quality_*.json
tests/test_agents/test_quality_assurance.py
tests/test_agents/test_quality_tools.py
tests/test_agents/test_quality_security.py
```

Các module nhỏ có thể gộp, nhưng phải giữ ranh giới profile/schema/tool/service/UI/test.

### 3.2 Shared files không tự sửa

```text
src/agents/contracts.py
src/agents/state.py
src/agents/graph.py
src/agents/router.py
src/agents/context_builder.py
src/agents/tools/registry.py
src/db/models.py
src/config.py
src/db/migrations/versions/*
```

Thay đổi registry để chuyển sang toolset rút gọn phải ở PR riêng hoặc được A review. Không đổi shared contract chỉ để né validator hiện có.

## 4. Contract của Quality Assurance Agent

### 4.1 Input

```text
AgentContext
├── runtime.agent_profile = quality_assurance
├── request.requested_scope = workspace
├── request.intent = quality_readiness | quality_brief
├── request.target_agent_workspace_id = quality-assurance workspace ID
├── actor.business_role = lead | member
└── authorization
    ├── decision = ALLOW
    ├── allowed_agent_workspace_ids = [target]
    ├── allowed_resource_ids = [linked, consented QA sources]
    └── consent_scope_hash
```

Sai bất kỳ điều kiện nào phải fail trước model và trước query.

### 4.2 Domain output

`QualityBriefPayload` dùng cấu trúc tối thiểu:

```json
{
  "headline": "string",
  "release_readiness": "READY|AT_RISK|NOT_READY",
  "test_progress": {
    "total": 0,
    "open": 0,
    "testing": 0,
    "passed": 0,
    "failed": 0,
    "blocked": 0
  },
  "critical_defects": [],
  "blocked_tests": [],
  "quality_risks": [],
  "reasons": [],
  "recommendations": [],
  "data_gaps": [],
  "source_ids": [],
  "generated_at": "ISO-8601"
}
```

Mỗi finding tối thiểu có `work_item_id`, `title`, `severity`, `quality_status` và `source_id`. `READY` không hợp lệ nếu còn data gap, critical defect mở, required check thiếu/chưa pass hoặc test failed/blocked.

### 4.3 WorkspaceBrief handoff

Quality producer ánh xạ payload vào common `WorkspaceBrief`:

- `brief_type=quality`.
- `producer_profile=quality_assurance`.
- `release_readiness` bắt buộc có.
- Source phải cùng QA Workspace hoặc là structured reference được policy cho phép.
- `generated_at`, `expires_at`, period và timezone phải hợp lệ.
- Delivery và Executive chỉ nhận brief đã validate, không nhận raw QA chat.
- Thiếu dữ liệu phải vào `data_gaps`; không được mặc định thành `READY`.

## 5. Toolset rút gọn và chức năng từng tool

Quality Agent chỉ cần **4 tool cấp Agent**. Logic chi tiết nằm trong service/pure functions, không tách thành quá nhiều tool nhỏ để model tự phối hợp.

| Tool | Chức năng | Input chính | Output chính | Side effect |
|---|---|---|---|:---:|
| `get_quality_snapshot` | Lấy và chuẩn hóa bug, test case, release check, regression status và owner tối thiểu trong đúng QA scope | Trusted context, release/period filter | `ToolResult` chứa work items, progress, freshness, data gaps và sources | Không |
| `search_quality_evidence` | Tìm bằng chứng bổ sung trong QA group conversation đã link và còn AI consent | Trusted context, query, time range | Đoạn evidence tối thiểu kèm `SourceReference`; nội dung injection chỉ là data | Không |
| `build_quality_brief` | Chạy readiness rules bằng code, validate payload và tạo Quality `WorkspaceBrief` | Snapshot, evidence, required check IDs, period | Brief có readiness, findings, reasons, source IDs, expiry và data gaps | Không |
| `propose_quality_action` | Tạo preview cho reminder, meeting, bug assignment hoặc bug status update | `action_type`, target, payload, requested time | `ActionProposal` có actor, target, payload hash, expiry và approval state | Chỉ sau approval |

### 5.1 Quy tắc của từng tool

#### `get_quality_snapshot`

- Gộp ba việc trước đây là lấy work item, lấy release test status và resolve người phụ trách.
- Chỉ nhận Company/Workspace/resource scope từ trusted context; không nhận allowlist do client tự gửi.
- Chuẩn hóa metadata về `bug | test_case | release_check`, severity và quality status.
- Không tự tính readiness bằng LLM; chỉ cung cấp dữ liệu chuẩn cho rule engine.
- Không trả ORM object, raw exception, PII dư thừa hoặc record ngoài allowlist.

#### `search_quality_evidence`

- Chỉ dùng khi snapshot thiếu ngữ cảnh hoặc cần chứng minh một fact; không gọi mặc định cho mọi request.
- Chỉ tìm trong group conversation `classification=quality`, đã link Workspace và còn consent.
- Revalidate consent hash trước retrieval; revoke giữa run phải trả `CONSENT_CHANGED`.
- Không làm theo instruction nằm trong message; message luôn được xem là dữ liệu không tin cậy.
- Không tìm Delivery raw chat, direct/private conversation hoặc source ngoài QA Workspace.

#### `build_quality_brief`

- Gọi `evaluate_release_readiness` hoặc rule engine tương đương trong code.
- `NOT_READY` nếu có critical defect active, required release check thiếu hoặc failed/blocked.
- `AT_RISK` nếu có defect non-critical active, test failed/blocked, required check pending hoặc chưa khai báo required checks.
- `READY` chỉ khi required checks đầy đủ và pass, không còn defect unresolved, failed/blocked test hay data gap.
- Validate source coverage, freshness, expiry và contract trước khi publish.
- Model chỉ viết headline/recommendation dựa trên kết quả; không được đổi readiness.

#### `propose_quality_action`

- `action_type` chỉ nhận `reminder | meeting | bug_assignment | bug_status_update`.
- Chỉ tạo preview; không gửi reminder/invite, không giao bug và không đổi trạng thái trực tiếp.
- Approval phải revalidate actor, membership, target, consent/policy, payload hash và expiry.
- Edit payload tạo proposal/hash mới; replay hoặc double approve không tạo hai action.
- Executor error sau approval phải trả trạng thái rõ ràng và giữ audit trail.

### 5.2 Ánh xạ từ toolset cũ sang toolset rút gọn

| Tool cũ | Tool mới | Lý do |
|---|---|---|
| `get_quality_work_items` | `get_quality_snapshot` | Cùng đọc QA work-item data |
| `get_release_test_status` | `get_quality_snapshot` | Status là một phần của snapshot |
| `get_quality_people` | `get_quality_snapshot` | Chỉ cần owner tối thiểu đi kèm item |
| `search_quality_messages` | `search_quality_evidence` | Tên mới mô tả đúng mục đích tìm bằng chứng |
| `build_quality_brief` | `build_quality_brief` | Giữ nguyên vì là boundary tạo contract |
| `propose_quality_reminder` | `propose_quality_action` | Gộp các action vào một proposal contract |
| `propose_quality_meeting` | `propose_quality_action` | Gộp các action vào một proposal contract |

Registry có thể giữ alias cũ trong giai đoạn chuyển tiếp, nhưng profile mới chỉ expose bốn tên mới. Alias không được tạo đường bypass policy hoặc approval.

## 6. Kế hoạch và báo cáo thực hiện 7 ngày

### 6.1 Trạng thái tổng hợp

| Ngày | Phạm vi | Trạng thái | Evidence chính |
|---:|---|---|---|
| 1 | Contract, schema, readiness rules, profile và migration preflight | `PASS` | PostgreSQL 17; 15 golden readiness cases; schema/profile tests |
| 2 | Scoped service và toolset rút gọn | `IN_PROGRESS` | Scoped fixture snapshot + DB evidence query; 13 targeted tests |
| 3 | Runtime và Quality WorkspaceBrief | `PENDING` | Cập nhật sau khi thực hiện |
| 4 | UI và HITL proposal | `PENDING` | Cập nhật sau khi thực hiện |
| 5 | Eval và security hardening | `PENDING` | Cập nhật sau khi thực hiện |
| 6 | Real integration, E2E và performance | `PENDING` | Cập nhật sau khi thực hiện |
| 7 | Freeze, provision và bàn giao | `PENDING` | Cập nhật sau khi thực hiện |

Trạng thái chỉ chuyển sang `PASS` khi deliverable và gate của ngày đó đều có evidence. Nếu chưa chạy DB/runtime/E2E thật thì phải giữ `PENDING`, `PARTIAL` hoặc `BLOCKED`.

## Ngày 1 — Khóa Quality contract, readiness rules và profile

**Trạng thái:** `PASS` — thực hiện ngày 2026-08-19.

### Sáng — 3 giờ

- Xác nhận Workspace/profile/flag và đọc 15 golden cases.
- Chốt metadata `work_item_type`, `severity`, `quality_status`.
- Chốt thứ tự ưu tiên `NOT_READY → AT_RISK → READY`.
- Tạo fixture happy, empty, partial, critical defect và missing check.

### Chiều — 4 giờ

- Tạo strict schema và pure readiness rules.
- Tạo profile/prompt v1 với evidence-first guardrails.
- Viết unit tests cho boundary status và data gaps.
- Đối chiếu output với quality fixture trong dataset.

### PR-C1 — Quality schema/profile skeleton

Deliverable:

- Strict schemas, versioned prompt và deterministic readiness evaluator.
- Tối thiểu 15 readiness cases cùng unit tests.

Gate cuối ngày:

- 5 `READY`, 5 `AT_RISK`, 5 `NOT_READY` pass.
- `READY + data_gaps` bị reject.
- Model không được tự ghi đè readiness.
- Trạng thái hiện tại: **đã hoàn thành**, có run report Ngày 1.

### Báo cáo thực hiện Ngày 1

#### Kết quả code và contract

- Đã tạo `QualityWorkItem`, `QualityTestProgress`, `QualityItemFinding` và `QualityReadinessAssessment` trong `src/agents/schemas/quality.py`.
- Metadata MVP đã khóa:

  | Field | Giá trị hợp lệ |
  |---|---|
  | `work_item_type` | `bug`, `test_case`, `release_check` |
  | `severity` | `low`, `medium`, `high`, `critical` |
  | `quality_status` | `open`, `testing`, `passed`, `failed`, `blocked` |

- Schema strict, immutable và bắt buộc `source_id`; finding không có nguồn bị reject.
- Đã tạo profile/prompt `quality-assurance-v1` trong `src/agents/profiles/quality_assurance.py`.
- `evaluate_release_readiness` chạy bằng code; model chỉ được diễn giải, không được tự đổi readiness.
- Đã khóa guardrail: không đọc raw Delivery conversation, không tự hạ severity/đóng bug/đổi status và mọi side effect phải qua human confirmation.

#### Readiness rules đã kiểm chứng

1. `NOT_READY` nếu có critical bug chưa pass, thiếu required release check hoặc required check đang `failed`/`blocked`.
2. `AT_RISK` nếu có bug non-critical chưa pass, test `failed`/`blocked`, required check còn `open`/`testing` hoặc chưa khai báo required checks.
3. `READY` chỉ khi có required checks, mọi check đều hiện diện và `passed`, không còn unresolved bug, failed/blocked test hoặc data gap.

Golden dataset `QLT-001` đến `QLT-015` đã được map thành 5 `NOT_READY`, 5 `AT_RISK` và 5 `READY`.

#### Database và migration evidence

- Môi trường chạy: PostgreSQL 17, local test database `qa_day1_20260819`.
- `alembic upgrade head`: `PASS`, revision `20260819_15 (head)`.
- Chạy upgrade lần hai: `PASS`, xác nhận idempotency.
- Bảng `agent_workspaces` và `agent_workspace_memberships` tồn tại.
- Partial unique index `uq_agent_workspace_active_lead` tồn tại với điều kiện `business_role = 'lead' AND status = 'active'`.
- Constraints `ck_memory_type` và `ck_memory_sensitivity` tồn tại đúng một lần.
- Migration `20260813_12_timeline_memory.py` đã được làm idempotent để tránh PostgreSQL `DuplicateObjectError` khi model-created tables đã có check constraints.

#### Deliverables Ngày 1

- `src/agents/schemas/quality.py`
- `src/agents/profiles/quality_assurance.py`
- `tests/test_agents/test_quality_assurance.py`
- 15 quality fixture expectations trong `eval/datasets/multi_agent_workspace_v1.jsonl`

#### Chưa thuộc phạm vi Ngày 1

- Chưa nối Quality Agent vào `/chat` hoặc runtime thật.
- Chưa đọc scoped QA data từ database thật.
- Chưa thực thi side effect.
- Chưa provision Workspace hoặc bật Role C; các bước này thuộc Ngày 7 sau khi service, tools, consent và E2E hoàn tất.

#### Verification bổ sung ngày 2026-08-20

- `pytest tests/test_agents/test_quality_assurance.py tests/test_multi_agent_dataset.py -q`: `20 passed`, gồm case explicit reject `READY + data_gaps`.
- `scripts/generate_multi_agent_dataset.py --check`: `PASS`, dataset giữ nguyên 150 case.
- `scripts/validate_multi_agent_dataset.py`: `PASS`, 15 case `quality_readiness` hợp lệ.
- Ruff cho các artifact Ngày 1 chạy với `--no-cache`: `PASS`; cache mặc định của workspace không ghi được do quyền trên `.ruff_cache`, không phải lỗi source.

## Ngày 2 — Scoped service và toolset rút gọn

**Trạng thái:** `IN_PROGRESS` — bắt đầu ngày 2026-08-20; phần fixture/scoped evidence đã có, scoped work-item DB thật vẫn chờ dependency A.

### Sáng — 3 giờ

- Viết `quality_workspace_service.py` với Company ID, Agent Workspace ID và allowed resource IDs explicit.
- Thiết kế normalized snapshot và timeout/error contract.
- Chốt mapping tool cũ → bốn tool mới với A.

### Chiều — 4 giờ

- Implement `get_quality_snapshot` và `search_quality_evidence`.
- Mỗi record/finding trả source và freshness.
- Thêm resource guard, consent-hash revalidation và error normalization.

### PR-C2 — Quality scoped reads

Test bắt buộc:

- QA lead/member được ALLOW.
- Outsider, Delivery member và guessed resource ID bị DENY trước query.
- Private/direct conversation không đi vào source.
- Revoke consent trả `CONSENT_CHANGED`.
- Prompt injection không đổi allowlist.

Gate cuối ngày:

- Unauthorized leakage bằng 0.
- Không có Company-wide fallback.
- Snapshot đầy đủ hoặc nêu data gap rõ ràng.

### Báo cáo tiến độ Ngày 2 — 2026-08-20

#### Đã thực hiện

- C2-01 `DONE`: tạo `QualityQueryScope` và `QualityWorkItemRepository`; mọi query bắt buộc có Company ID, Agent Workspace ID và `allowed_resource_ids`, không có tham số mặc định để query toàn Company.
- C2-02 `PARTIAL`: tạo `InMemoryQualityWorkItemRepository` và `get_quality_snapshot` cho fixture đã chứng minh nguồn. Adapter lọc đồng thời Company, QA Workspace, release/period và source allowlist; repository trả record ngoài scope bị chặn bằng `REPOSITORY_SCOPE_VIOLATION`.
- C2-03 `DONE_FOR_CONVERSATION_DB`: `search_quality_evidence` query database thật, chỉ lấy conversation `group`, `classification=quality`, đã link đúng QA Workspace, đang `ai_enabled` và nằm trong allowlist sau revalidation.
- C2-04 `DONE`: thêm normalized snapshot/evidence schemas, source/freshness timestamp, `SUCCESS | PARTIAL | ERROR`, timeout và generic error message không lộ raw exception.
- C2-05 `DONE_FOR_CURRENT_ADAPTERS`: thêm tool/security tests cho lead/member, denied context, Delivery profile, guessed resource, private/direct, unlinked, Delivery-classified source, consent revoke, membership revoke, wildcard và prompt injection.

#### Test/gate đã chạy

- `pytest tests/test_agents/test_quality_tools.py tests/test_agents/test_quality_security.py -q`: `13 passed`.
- Regression gộp Quality + dataset + Agent Workspace authorization: `44 passed`.
- Ruff với `--no-cache` trên service, hai tool, Quality schemas và hai test module: `PASS`.
- Unauthorized leakage trong test matrix hiện tại: `0`; prompt injection được trả như evidence data và không đổi allowlist.

#### Dependency và giới hạn còn lại

- `WAIT_A_SCOPE`: chưa có shared scoped work-item query/persistence nên snapshot hiện chỉ dùng fixture adapter; không tuyên bố đã đọc work item DB thật và không thêm Company-wide fallback.
- `WAIT_A_REVIEW`: chưa sửa shared tool registry hoặc alias cũ; việc bind bốn tool để sang Ngày 3/PR riêng có A review.
- Vì hai dependency trên, Ngày 2 giữ `IN_PROGRESS`, chưa chuyển `PASS` dù các adapter hiện tại và negative tests đã xanh.

## Ngày 3 — Runtime và Quality WorkspaceBrief

**Trạng thái:** `PENDING` — cập nhật kết quả, test và evidence tại đây sau khi thực hiện.

### Sáng — 3 giờ

- Viết profile handler nhận trusted `AgentContext`.
- Bind đúng bốn tool; tool ngoài allowlist phải fail.
- Giới hạn tool/token budget và vòng lặp.
- Tách rule engine khỏi phần diễn giải bằng model.

### Chiều — 4 giờ

- Implement `build_quality_brief`.
- Validate source Workspace, readiness, freshness, period và expiry.
- Nối profile runner của A hoặc giữ adapter riêng nếu dependency chưa sẵn sàng.
- Tạo brief candidate cho B và D bằng contract, không truyền raw message.

### PR-C3 — Quality Agent read-only + brief producer

Gate cuối ngày:

- 15/15 structural readiness cases pass.
- Critical bug active luôn `NOT_READY`.
- Empty/partial data không bao giờ trả `READY`.
- B và D đọc được fixture qua common contract.

## Ngày 4 — UI vertical slice và HITL proposal

**Trạng thái:** `PENDING` — cập nhật kết quả, test và evidence tại đây sau khi thực hiện.

### Sáng — 3 giờ

- Tạo `QualityAgentPage` và cards cho readiness, test progress, defects, blockers và sources.
- Hiển thị loading, empty, denied, partial, stale, error và feature-disabled state.
- Không hiển thị raw policy detail hoặc stack trace.

### Chiều — 4 giờ

- Implement `propose_quality_action` và approval card.
- Preview hiển thị actor, action, target, payload, time và expiry.
- Approve chỉ gọi shared executor; edit tạo hash mới.
- Test double-click/double approve và permission revoke.

### PR-C4 — Quality UI + proposal flow

Gate cuối ngày:

- Không có side effect trước approval.
- Payload đổi bắt buộc confirm lại.
- Revoke role trước approve làm proposal invalid.
- Outsider sửa URL vẫn không mở được QA page.

## Ngày 5 — Eval, security và edge cases

**Trạng thái:** `PENDING` — cập nhật kết quả, test và evidence tại đây sau khi thực hiện.

### Sáng — 3 giờ

- Nối quality subset JSONL vào evaluator thật.
- Chạy readiness, routing, permission, injection, HITL và revoke cases.
- Ghi model/prompt/schema/policy version trong report.

### Chiều — 4 giờ

- Sửa stale/partial/conflicting evidence behavior.
- Fuzz Workspace/resource/release IDs.
- Kiểm tra model không hạ severity, đóng bug hoặc biến thiếu dữ liệu thành fact.
- Phân loại failure: data, policy, tool, rule, prompt, model hoặc UI.

### PR-C5 — Quality eval/security hardening

Gate cuối ngày:

- Quality routing `>=95%`.
- Source coverage cho finding quan trọng `=100%`.
- Unauthorized leakage `=0`.
- HITL coverage cho side effect `=100%`.

## Ngày 6 — Integration, performance và demo rehearsal

**Trạng thái:** `PENDING` — cập nhật kết quả, test và evidence tại đây sau khi thực hiện.

### Sáng — 3 giờ

- Thay mock bằng scoped DB service, brief store và executor đã qua gate.
- Chạy migration head trên database sạch và database có dữ liệu.
- Seed QA dataset synthetic, idempotent.
- Kiểm tra revoke/suspend/feature flag ở request kế tiếp.

### Chiều — 4 giờ

- Chạy E2E bằng lead/member/outsider/admin.
- Đo query, latency, token và tool budget; loại N+1/retrieval dư.
- Xác minh Executive chỉ đọc validated brief.
- Rehearse demo “Release này có sẵn sàng không, vì sao?”.

### PR-C6 — Quality integration candidate

Gate cuối ngày:

- Read-only E2E chạy bằng dữ liệu thật.
- HITL E2E có revalidation và idempotency.
- B và D dùng brief thật mà không đổi parser/contract.
- Backend tests, User build và critical security tests xanh.

## Ngày 7 — Freeze, provision và bàn giao

**Trạng thái:** `PENDING` — cập nhật kết quả, test và evidence tại đây sau khi thực hiện.

### Sáng — 3 giờ

- Không thêm tính năng; chỉ sửa P0/P1.
- Chạy regression, dataset, migration và frontend build.
- Provision/verify Workspace trên staging bằng Platform Admin.
- Pin prompt/schema/policy/model versions.

### Chiều — 4 giờ

- Ghi evidence happy, denial, stale/partial và HITL.
- Viết release note, known limits, flag và rollback runbook.
- Bàn giao Quality brief thật cho B và D.
- Demo 2 phút và ký Quality sign-off.

### PR-C7 — Quality release evidence

Gate cuối ngày:

- Không còn critical/open security issue.
- Đúng một active QA lead; lead/member discovery hoạt động.
- Feature flag bật/tắt không phá Personal hoặc Delivery flow.
- Executive consume được brief thật mà không thấy raw QA data.

## 7. PR map và thứ tự merge

| PR | Nội dung | Phụ thuộc | Reviewer | Kích thước mục tiêu |
|---|---|---|---|---:|
| C1 | Schema/profile/readiness rules | Shared contract v1 | A + B + D | ≤450 dòng |
| C2 | Scoped service + simplified read tools | Scope/resource baseline | A | ≤700 dòng |
| C3 | Runtime + QualityBrief producer | C1+C2, brief contract | A + B + D | ≤700 dòng |
| C4 | UI + unified proposal adapter | Shared UI/HITL interface | A | ≤700 dòng |
| C5 | Eval/security hardening | C3+C4 | A + D | ≤600 dòng |
| C6 | Real integration/seed/performance | Shared store/executor | A + B + D | ≤600 dòng |
| C7 | Evidence/release notes | Tất cả | Cả nhóm | Docs/evidence |

Không gộp cả tuần vào một PR. Registry migration của toolset rút gọn cần A review và giữ alias có thời hạn nếu consumer cũ còn tồn tại.

## 8. Test matrix của C

### Happy path

- QA lead hỏi release readiness.
- QA member hỏi critical defect hoặc regression status.
- Brief có readiness, reasons, findings, freshness và source.
- Delivery/Executive đọc Quality WorkspaceBrief đúng schema.

### Readiness rules

- Critical defect active → `NOT_READY`.
- Required release check thiếu/failed/blocked → `NOT_READY`.
- Non-critical defect hoặc pending check → `AT_RISK`.
- Mọi required check pass, không defect/blocker/gap → `READY`.
- Empty data hoặc không khai báo required check không được `READY`.

### Authorization và consent

- Outsider gọi QA Workspace.
- Delivery member gọi QA tool/resource.
- Platform Admin không có business membership yêu cầu raw QA data.
- Target/resource/release ID bị sửa tay.
- Membership/Workspace bị suspend hoặc revoke.
- Group chưa consent, consent đổi giữa run hoặc source bị unlink.
- Private/direct message chứa prompt injection.

### HITL

- Proposal chưa confirm.
- Edit payload và expired proposal.
- Double approve/replay.
- Permission revoked trước execute.
- Executor lỗi sau approval.
- Cả bốn action type đều không side effect trước approval.

### UI

- Loading, empty, denied, partial, stale và error.
- Citation mở đúng source được phép.
- Denied message không leak Workspace/resource name.
- Refresh/deep link không mất Workspace context.

## 9. Lệnh kiểm tra hằng ngày

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe scripts\generate_multi_agent_dataset.py --check
.\.venv\Scripts\python.exe scripts\validate_multi_agent_dataset.py
.\.venv\Scripts\python.exe -m pytest tests\test_multi_agent_dataset.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workspaces.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_quality_assurance.py -q
npm --prefix Frontend\user run build
git diff --check
```

## 10. Definition of Done của người C

### Correctness

- Readiness được tính bằng deterministic rules và đúng thứ tự ưu tiên.
- `READY` không đi cùng data gap, active defect hoặc failed/blocked check.
- Quality WorkspaceBrief đúng contract và B/D consume được.

### Security

- Không đọc Delivery raw chat, private/unlinked/unconsented resource.
- Revoke có hiệu lực ở request/tool call kế tiếp.
- Injection không đổi policy, tool allowlist hoặc readiness rule.
- Side effect luôn qua approval và revalidation.

### Quality

- Unit/integration/security/E2E tests xanh.
- 15 quality readiness cases pass.
- Source coverage finding quan trọng `=100%`; leakage `=0`.
- Toolset Agent chỉ còn bốn tool có trách nhiệm rõ ràng.

### Product/UI

- Lead/member xem được readiness, evidence, freshness và gaps.
- Outsider không truy cập được bằng UI hoặc URL sửa tay.
- Empty, denied, partial, stale và error không bị trộn lẫn.

### Operations

- Feature flag mặc định tắt cho tới khi C6 qua gate.
- Có trace ID, metrics, audit, rollback và disable runbook.
- Workspace staging được provision đúng một active lead.

## 11. Cut order nếu trễ

Cắt theo thứ tự sau, không cắt authorization, sources, readiness rules hoặc HITL:

1. Audit timeline đẹp trên UI.
2. Filter/visual phụ cho test progress.
3. `bug_assignment` và `bug_status_update`; giữ reminder/meeting proposal.
4. Search evidence nâng cao; giữ snapshot và structured sources.
5. Performance tuning không critical; ghi waiver với số đo thực tế.

MVP tối thiểu vẫn phải có scoped snapshot, deterministic readiness, validated Quality brief, source coverage, denial tests và không side effect trước approval.

## 12. Báo cáo cuối ngày của C

Mỗi ngày báo cáo ngắn theo form:

```text
Ngày / PR:
Đã hoàn thành:
Test/gate đã chạy:
Evidence:
Dependency đang chờ:
Risk hoặc data gap:
Việc đầu tiên ngày mai:
```

Không dùng “đã xong” nếu mới chạy fixture trong khi task yêu cầu DB, runtime hoặc E2E thật.

## 13. Backlog chi tiết theo từng tác vụ

### 13.1 Các tác vụ nghiệp vụ Agent phải thực hiện

| Capability ID | Tác vụ | Input | Output bắt buộc | Không được làm | Ngày |
|---|---|---|---|---|---:|
| QLT-C01 | Xác thực QA request | Trusted `AgentContext` | Allow/deny trước model | Tin workspace/resource ID từ client | 2–3 |
| QLT-C02 | Lấy Quality snapshot | Scoped work items | Normalized tests/defects/checks/owners + sources | Query Company-wide | 2 |
| QLT-C03 | Tìm QA evidence | Consented QA conversations | Minimal evidence + source/freshness | Đọc private/Delivery raw chat | 2 |
| QLT-C04 | Tính readiness | Snapshot + required checks | Deterministic readiness + reasons/gaps | Để model tự chọn readiness | 1–3 |
| QLT-C05 | Tạo Quality brief | Valid assessment | Versioned brief + expiry + sources | Publish invalid/unsourced brief | 3 |
| QLT-C06 | Trả lời user | Brief/tool result | Headline, facts, risks, gaps, recommendations | Che tool error/data gap | 3–4 |
| QLT-C07 | Đề xuất QA action | Actor + target + payload | `ActionProposal` preview | Thực thi trước approval | 4 |
| QLT-C08 | Phản ứng revoke/stale/error | Current policy + freshness | Deny/partial/stale response | Dùng cache/quyền cũ | 5–6 |
| QLT-C09 | Handoff cho Delivery/Executive | Valid Quality brief | Structured consumer payload | Truyền raw QA messages | 3–6 |

### 13.2 Task board theo ngày

#### Ngày 1 — 7 giờ: contract, rules và profile

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C1-01 | 1h | Map 15 quality cases | Case matrix | Mỗi case map vào rule/reason |
| C1-02 | 1.5h | Tạo strict Quality schemas | `schemas/quality.py` | Extra forbid, immutable, source required |
| C1-03 | 2h | Viết readiness rules | Pure functions | Boundary tests pass |
| C1-04 | 1.5h | Viết profile/prompt v1 | `profiles/quality_assurance.py` | Evidence-first, no scope expansion |
| C1-05 | 1h | Unit/contract tests | Test module | 15 cases và invalid payload pass |

#### Ngày 2 — 7 giờ: scoped service và simplified tools

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C2-01 | 1h | Định nghĩa scoped service interface | Quality service | Mọi query có explicit scope |
| C2-02 | 2h | Implement `get_quality_snapshot` | Snapshot tool | Không Company-wide fallback |
| C2-03 | 1.5h | Implement `search_quality_evidence` | Evidence tool | Chỉ linked group + consent |
| C2-04 | 1h | Chuẩn hóa tool result/error/freshness | Tool helpers | Không raw ORM/exception |
| C2-05 | 1.5h | Tool/security tests | Test modules | Cross-workspace leakage = 0 |

#### Ngày 3 — 7 giờ: runtime và WorkspaceBrief

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C3-01 | 1h | Tạo Quality profile handler | Profile runner | Chỉ trusted context/profile |
| C3-02 | 1h | Bind bốn-tool allowlist | Registry adapter | Tool ngoài list bị chặn |
| C3-03 | 2h | Implement `build_quality_brief` | Brief producer | Rule/source/time validate |
| C3-04 | 1h | Thêm stale/partial behavior | Validator/service | Không trình bày stale là current |
| C3-05 | 1h | Contract tests với B/D | Handoff tests | Consumer không parse text tự do |
| C3-06 | 1h | Tạo sample output | Quality fixture | IDs/schema/source ổn định |

#### Ngày 4 — 7 giờ: UI và unified HITL action

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C4-01 | 1h | Nối profile vào invocation adapter | API integration | Auth/context trước model |
| C4-02 | 2h | Tạo Quality page/cards/states | UI components | Source/freshness/gap rõ ràng |
| C4-03 | 2h | Implement `propose_quality_action` | Proposal adapter | Bốn action type, no direct execute |
| C4-04 | 1h | Approval/revalidation/idempotency tests | HITL tests | Edit/replay/revoke đúng |
| C4-05 | 1h | UI build/smoke/accessibility | Evidence | Production build pass |

#### Ngày 5 — 7 giờ: eval và security hardening

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C5-01 | 1h | Nối quality cases vào evaluator | Runner mapping | Version metadata đầy đủ |
| C5-02 | 1h | Chạy/tune readiness cases | Eval result | Không sửa expected để né lỗi |
| C5-03 | 1.5h | Cross-workspace/IDOR tests | Security tests | Leakage = 0 |
| C5-04 | 1h | Injection/revoke/consent tests | Security tests | Fail closed |
| C5-05 | 1.5h | Ambiguity/stale/conflict tests | Domain tests | Gap/reason đúng |
| C5-06 | 1h | Failure report và fixes | Eval report | Root cause rõ ràng |

#### Ngày 6 — 7 giờ: dữ liệu thật, E2E và hiệu năng

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C6-01 | 1h | Thay mock bằng shared implementation | Integrated branch | Không local bypass |
| C6-02 | 1h | Seed QA dataset idempotent | Seed + manifest | Chạy lại không nhân bản |
| C6-03 | 1.5h | E2E lead/member/outsider/admin | E2E evidence | Đúng allow/deny |
| C6-04 | 1h | E2E consent/revoke/HITL | E2E evidence | Revalidate/idempotency pass |
| C6-05 | 1h | Đo query/LLM/tool latency | Performance report | Không N+1/retrieval dư |
| C6-06 | 1h | Handoff test với B/D | Consumer evidence | Không raw source leakage |
| C6-07 | 0.5h | Rehearse demo | Demo checklist | Readiness có reason/source |

#### Ngày 7 — 7 giờ: freeze và bàn giao

| Task ID | Thời lượng | Việc thực hiện | Artifact | Acceptance |
|---|---:|---|---|---|
| C7-01 | 1.5h | Chạy regression/dataset/build | Test report | Tất cả Quality gates xanh |
| C7-02 | 1h | Chỉ sửa P0/P1 | Final fixes | Không thêm tính năng |
| C7-03 | 1h | Provision/verify staging Workspace | Provision evidence | Đúng một active lead |
| C7-04 | 1h | Ghi happy/deny/stale/HITL evidence | Evidence bundle | Trace/source nhìn thấy được |
| C7-05 | 1h | Bàn giao brief thật cho B/D | Brief + proof | Consumer đọc được |
| C7-06 | 1h | Viết flag/rollback/known limits | Runbook | Disable an toàn |
| C7-07 | 0.5h | Demo/sign-off | Sign-off record | A/B/D chấp thuận |

### 13.3 Việc có thể bắt đầu ngay và việc đang bị chặn

| Nhóm việc | Trạng thái bắt đầu | Task tương ứng | Ghi chú |
|---|---|---|---|
| Schema, rules, profile và tests | `DONE_DAY1` | C1-01 → C1-05 | Đã có run report |
| Tool interface + fixture implementation | `IN_PROGRESS_DAY2` | C2-01 → C2-05 | Fixture snapshot và DB evidence đã có; chờ scoped work-item query thật |
| Brief validator/producer in-memory | `READY_NOW` | C3-03 → C3-06 | Chưa gọi là published brief |
| UI bằng fixture | `READY_NOW` | C4-02 | Không tuyên bố E2E |
| Structural/golden evaluator | `READY_NOW` | C5-01 → C5-02 | Live runner nối sau |
| Registry migration sang bốn tool | `WAIT_A_REVIEW` | C3-02 | Cần A review shared file |
| Real work-item query | `WAIT_A_SCOPE` | C2-02, C6-01 | Chờ scoped query policy |
| Invocation API thật | `WAIT_A_RUNTIME` | C4-01 | Chờ router/context từ API |
| Durable brief publication | `WAIT_A_STORE` | C3-03, C6-01 | Chờ store/lineage/audit |
| Side-effect execution | `WAIT_A_HITL` | C4-03 → C4-04 | C vẫn tạo/test proposal object |
| Structured Delivery reference | `WAIT_B_BRIEF` | C3-05, C6-06 | Không đọc raw Delivery chat |

Trong khi chờ dependency, C tiếp tục phần `READY_NOW`; không tạo đường tắt quyền, tool alias không kiểm soát hoặc schema riêng để “cho chạy được”.
