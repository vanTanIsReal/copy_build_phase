# Kiến trúc và sơ đồ các nhánh — Orbit CHAT-01

> Ba vai trò nghiệp vụ · Ba role-agent · Một Orchestrator · Policy trước tool · HITL trước side effect

## 1. Hiện trạng và kiến trúc đích

### CURRENT — nền tảng đang có trên `origin/main`

Hệ thống hiện có một planner dùng chung trong `src/agents`, gọi các tool tóm tắt, task, reminder,
calendar, memory, people và search. Graph cơ bản là `planner → tools → planner/end`; user UI và admin
UI đã tách riêng, còn short-term state dùng LangGraph checkpoint. Đây là nền tảng tốt để mở rộng
nhưng **chưa phải ba agent độc lập theo vai trò**. Compact node, thread TTL, personal timeline và
governed long-term memory ở phần kế tiếp là thiết kế đích; tại thời điểm tài liệu được nhập vào
`main`, phần code tương ứng vẫn đang được phát triển trên nhánh tích hợp.

```mermaid
flowchart LR
    User[User UI] --> API[FastAPI]
    Admin[Admin UI] --> API
    API --> Auth[Auth + authorization + consent]
    API --> Planner[Shared Planner]
    Planner --> Tools[ToolNode / tool registry]
    Tools --> Planner
    Tools --> PG[(Postgres domain + long-term memory)]
    Tools --> Redis[(Redis)]
    Tools --> GCal[Google Calendar]
    Planner --> HITL[Existing tool interrupt / confirm]
    API --> Audit[Audit + usage]
```

### TARGET foundation — Timeline và memory cần tích hợp

```mermaid
flowchart TB
    MSG[(Consent-authorized messages)] --> TL[Personal Timeline Projection]
    TASK[(Personal tasks)] --> TL
    REM[(Reminders)] --> TL
    CAL[Per-user Google Calendar] --> TL
    TL --> API[GET /api/v1/timeline]
    TL --> TOOL[get_personal_timeline tool]

    REQ[Agent request] --> CP[LangGraph checkpoint]
    CP --> ST[Recent messages + pending HITL]
    ST --> COMPACT[Deterministic compaction]
    COMPACT --> CP
    THREAD[(agent_threads: owner/workspace/TTL)] --> CP

    MEM[(Long-term memories)] --> RETRIEVE[Owner/workspace/type/expiry filter]
    RETRIEVE --> CONSENT{Source consent still valid?}
    CONSENT -->|yes or manual memory| AGENT[search_my_memories]
    CONSENT -->|no| DROP[Exclude from retrieval]
```

- Timeline sẽ là projection read-only, mặc định gộp task/reminder/calendar; message chỉ được thêm khi
  yêu cầu rõ và vẫn qua membership + consent. Calendar lỗi trả partial result cùng source status.
- Short-term checkpoint sẽ sống theo `thread_id`, persist bằng PostgreSQL ở production và được compact khi
  quá `AGENT_MAX_THREAD_MESSAGES`; thread metadata hết hạn theo `AGENT_THREAD_RETENTION_DAYS`.
- Long-term memory sẽ hỗ trợ `preference|relationship|episodic|semantic`, `source_message_ids`,
  `consent_scope_hash`, `sensitivity`, `confidence`, `expires_at` và `last_accessed_at`.
- Retrieval giai đoạn đầu dùng keyword search có governance; semantic/vector ranking là TARGET/P1.

### TARGET — vertical slice trong 7 ngày

Không nhân ba toàn bộ hạ tầng. Ba agent là ba policy/prompt/tool profile chạy trên một orchestration
core chung.

```mermaid
flowchart TB
    subgraph L1[1. Người dùng và giao diện]
      CEO[Sếp]
      MGR[Trưởng phòng]
      EMP[Nhân viên]
      OPS[Platform Admin - control plane]
      UI[User App: Assistant / Inbox / Calendar / Memory]
      AUI[Admin App: Usage / Audit / Health / Prompt versions]
      CEO --> UI
      MGR --> UI
      EMP --> UI
      OPS --> AUI
    end

    subgraph L2[2. API và điều phối]
      AUTH[Authentication + Role/Scope Resolver]
      ORCH[LangGraph Orchestrator]
      ROUTE[Intent + Role Router]
      POLICY[Policy Engine]
      HITL[Approval Service / HITL]
      AUDIT[Audit + Usage + Trace]
      UI --> AUTH --> ORCH --> ROUTE
      AUI --> AUTH
      ROUTE --> POLICY
    end

    subgraph L3[3. Role-agent profiles]
      EA[Executive Agent]
      MA[Manager Agent]
      WA[Employee Agent]
      ROUTE --> EA
      ROUTE --> MA
      ROUTE --> WA
    end

    subgraph L4[4. Shared capabilities]
      SUM[Summarize]
      EXT[Extract task/date]
      SEARCH[Search / retrieval]
      MEM[Memory]
      CAL[Calendar]
      REM[Reminder / task]
      PRO[Proactive detector]
      EA --> SUM
      EA --> SEARCH
      MA --> SUM
      MA --> SEARCH
      MA --> EXT
      WA --> SUM
      WA --> EXT
      WA --> SEARCH
      WA --> MEM
      WA --> CAL
      WA --> REM
    end

    subgraph L5[5. Dữ liệu và external tools]
      MSG[(Authorized internal chat)]
      DB[(Postgres)]
      CACHE[(Redis / BullMQ)]
      VECTOR[(Qdrant or pgvector - optional)]
      GCAL[Google Calendar API]
      WS[WebSocket notifications]
    end

    POLICY -. pre-check and per-tool check .-> EA
    POLICY -.-> MA
    POLICY -.-> WA
    CAL --> HITL --> GCAL
    REM --> HITL --> DB
    SUM --> MSG
    EXT --> MSG
    SEARCH --> MSG
    SEARCH --> VECTOR
    MEM --> DB
    PRO --> CACHE --> WS
    ORCH --> AUDIT
    POLICY --> AUDIT
    HITL --> AUDIT
```

## 2. Trục điều phối chung

Mọi nhánh đều dùng cùng một trục; role-agent không tự gọi tool ngoài trục này.

```mermaid
flowchart LR
    A[Request or message event] --> B[Authenticate]
    B --> C[Resolve workspace, business role, department]
    C --> D[Classify intent and requested scope]
    D --> E{Policy pre-check}
    E -->|DENY| X[Safe refusal + audit]
    E -->|MASK| F[Mask / reduce scope]
    E -->|ASK_CLARIFY| Q[Ask one precise question]
    E -->|ALLOW| G[Retrieve least context]
    F --> G
    G --> H[Selected role-agent plans]
    H --> I{Tool policy check}
    I -->|read allowed| J[Execute read tool]
    I -->|side effect| K[Preview + HITL]
    I -->|deny| X
    K -->|confirmed payload hash| L[Execute idempotently]
    K -->|edit| M[Re-plan and re-confirm]
    K -->|reject/expire| N[No action]
    J --> O[Validate output schema]
    L --> O
    O --> P[Audit metadata + usage]
    P --> R[Response / WebSocket]
```

## 3. Ba nhánh agent

### Nhánh A — Employee Agent

```mermaid
flowchart LR
    U[Nhân viên] --> R[Employee Agent]
    R --> P{Permission + consent}
    P -->|no| D[Deny / ask user to grant consent]
    P -->|yes| S[Search unread or selected messages]
    S --> C[Summarize + extract commitments]
    C --> V{Confidence and completeness}
    V -->|low / ambiguous| Q[Ask date, time, assignee or intent]
    V -->|sufficient| G[Show source-backed suggestions]
    G --> H{User action}
    H -->|dismiss| E[Save disposition only]
    H -->|edit| G
    H -->|confirm task| T[Create personal task]
    H -->|confirm reminder/calendar| X[HITL payload binding]
    X --> Y[Execute tool + audit]
```

Đầu vào thường gặp: “Tóm tắt tin chưa đọc”, “Tôi có việc gì?”, “Tạo lịch chiều mai”. Đầu ra chuẩn:
summary, decisions, tasks, open questions, sources và action cards. Agent chỉ dùng personal scope.

### Nhánh B — Manager Agent

```mermaid
flowchart LR
    U[Trưởng phòng] --> R[Manager Agent]
    R --> P{Manager relationship valid?}
    P -->|no| D[Deny]
    P -->|yes| T[Load team tasks and permitted summaries]
    T --> A[Prioritize overdue, due soon, blocked, unassigned]
    A --> I[Team Inbox / meeting brief]
    I --> X{Requested action}
    X -->|read own team| O[Return with sources]
    X -->|remind another person| H[HITL]
    X -->|cross department| C{Cross-scope policy}
    C -->|approved route| H
    C -->|not allowed| D
    H --> E[Execute + notify + audit]
```

Manager Agent không được lấy chat riêng của nhân viên chỉ vì user là trưởng phòng. Nó ưu tiên task
records và summary đã cấp quyền; raw message cần conversation membership/entitlement riêng.

### Nhánh C — Executive Agent

```mermaid
flowchart LR
    U[Sếp] --> R[Executive Agent]
    R --> P{Executive aggregate entitlement}
    P -->|no| D[Deny or downgrade to personal scope]
    P -->|yes| A[Fetch policy-filtered team aggregates]
    A --> M[Call Manager summaries when allowed]
    M --> S[Synthesize facts, risks and decisions]
    S --> V{Evidence sufficient?}
    V -->|no| G[State data gaps / request scope]
    V -->|yes| B[Executive Brief]
    B --> X{Side effect requested?}
    X -->|no| O[Return cited insight]
    X -->|yes| H[HITL + appropriate owner approval]
```

Executive Agent là agent tổng hợp, không phải “superuser đọc hết”. Nó dùng aggregate scope và có thể
gọi capability tổng hợp của Manager Agent qua Orchestrator; không bypass Policy Engine.

## 4. Nhánh proactive

Đường proactive phải bất đồng bộ để không làm chậm gửi tin.

```mermaid
sequenceDiagram
    participant C as Chat client
    participant E as Message API
    participant Q as Queue
    participant D as Commitment detector
    participant P as Policy/Consent
    participant U as User via WebSocket
    participant H as HITL
    participant T as Reminder/Calendar tool

    C->>E: Send message
    E-->>C: Accepted immediately
    E->>Q: message.created with authorized reference
    Q->>D: Analyze candidate asynchronously
    D->>P: Check consent, scope, preference
    alt not allowed or low confidence
        P-->>D: Drop / no notification
    else allowed and useful
        D->>U: Suggest task/reminder with source
        U->>H: Confirm or edit
        H->>T: Execute bound payload
        T-->>U: Result
    end
```

Rule gate trước model: bỏ qua reaction, emoji-only, system event và message không có tín hiệu hành
động; batch thread ngắn; dedupe theo source fingerprint.

## 5. Cây quyết định Policy Engine

```mermaid
flowchart TD
    R[Resource/tool request] --> A{Authenticated?}
    A -->|no| DENY[DENY]
    A -->|yes| B{Workspace and resource relationship valid?}
    B -->|no| DENY
    B -->|yes| C{Conversation consent / entitlement valid?}
    C -->|no| DENY
    C -->|yes| D{Sensitive fields present?}
    D -->|yes, mask sufficient| MASK[MASK then continue]
    D -->|yes, mask insufficient| DENY
    D -->|no| E{Required fields complete and confidence enough?}
    MASK --> E
    E -->|no| ASK[ASK_CLARIFY]
    E -->|yes| F{External or other-person side effect?}
    F -->|yes| HITL[HITL]
    F -->|no| ALLOW[ALLOW]
```

## 6. Scope dữ liệu trực quan

```mermaid
flowchart TB
    subgraph Personal[Personal scope]
      PC[Consent-enabled conversations]
      PT[My tasks/reminders]
      PM[My memory/calendar]
    end
    subgraph Team[Team scope]
      TT[Department task records]
      TS[Permitted group summaries]
      TW[Workload / overdue aggregates]
    end
    subgraph Aggregate[Executive aggregate scope]
      AK[Team KPIs]
      AR[Cross-team risks]
      AD[Decisions and data gaps]
    end
    EMP[Employee Agent] --> Personal
    MGR[Manager Agent] --> Team
    MGR -. own personal requests .-> Personal
    EXEC[Executive Agent] --> Aggregate
    EXEC -. own personal requests .-> Personal
    RAW[Private / sensitive raw chat] --> LOCK[Denied unless explicit resource-level entitlement]
```

Scope không phải vòng tròn kế thừa “sếp thấy mọi thứ”. Aggregate scope là một projection an toàn,
không đồng nghĩa union của toàn bộ raw messages.

## 7. LangGraph đích

```mermaid
stateDiagram-v2
    [*] --> load_identity
    load_identity --> classify_intent
    classify_intent --> policy_precheck
    policy_precheck --> denied: DENY
    policy_precheck --> clarify: ASK_CLARIFY
    policy_precheck --> retrieve_context: ALLOW/MASK
    retrieve_context --> route_agent
    route_agent --> executive_agent
    route_agent --> manager_agent
    route_agent --> employee_agent
    executive_agent --> policy_toolcheck
    manager_agent --> policy_toolcheck
    employee_agent --> policy_toolcheck
    policy_toolcheck --> execute_read: ALLOW
    policy_toolcheck --> human_confirm: HITL
    policy_toolcheck --> denied: DENY
    execute_read --> validate_result
    human_confirm --> execute_side_effect: confirmed
    human_confirm --> [*]: rejected/expired
    execute_side_effect --> validate_result
    validate_result --> audit_and_respond
    clarify --> [*]
    denied --> [*]
    audit_and_respond --> [*]
```

`AgentState` đích cần thêm: `business_role`, `department_ids`, `requested_scope`, `selected_agent`,
`intent`, `policy_decisions`, `consent_scope_hash`, `retrieved_source_ids`, `approval_request`,
`prompt_version`, `model_route`, `cost`, `trace_id` và `errors`.

## 8. Tool access matrix

| Tool/capability | Employee | Manager | Executive | Policy/HITL |
|---|:---:|:---:|:---:|---|
| `summarize_messages` | Personal | Team-permitted | Aggregate | Consent/scope check |
| `search_messages` | Personal | Team-permitted | Không mặc định raw | Resource authorization |
| `extract_tasks` | Personal | Team-permitted | Aggregate only | Confidence + schema |
| `get_team_inbox` | — | Own department | Aggregate view | Manager relation |
| `get_executive_brief` | — | — | Entitled unit | Aggregate policy |
| `create/update task` | Own | Own/team allowed | Usually delegate | Other person → HITL |
| `calendar create/update/delete` | Own | Own/allowed | Own/allowed | Luôn HITL |
| `create reminder` | Own | Own/team allowed | Usually delegate | Other person → HITL |
| `memory read/write/delete` | Own | Own + approved team aggregate | Own + aggregate | Owner/purpose/TTL |

## 9. Model routing, latency và cost

```mermaid
flowchart LR
    I[Intent] --> G{Complex multi-step or cross-team?}
    G -->|no| S[Small model: classify, summarize, extract]
    G -->|yes| L[Large model: bounded planning]
    S --> C[Schema validation]
    L --> C
    C -->|invalid| R[One repair attempt]
    C -->|valid| O[Policy/tool/output]
```

- Small model là mặc định; large model chỉ được router chọn cho reasoning tổng hợp phức tạp.
- Giới hạn số bước, tool calls, context tokens và wall-clock theo run.
- Search-first, summary cache và prompt version trong cache key.
- Không cache kết quả side effect hoặc dữ liệu sau khi consent bị revoke.

## 10. Triển khai

```mermaid
flowchart LR
    WEB[User/Admin web on Vercel] --> API[FastAPI container]
    API --> PG[(Postgres)]
    API --> RD[(Redis)]
    API --> WK[Worker: proactive/scheduler]
    WK --> RD
    WK --> PG
    API --> LLM[LLM providers]
    API --> GC[Google Calendar]
    API --> WS[WebSocket gateway]
    OBS[Metrics/log/audit without raw content] <-- API
    OBS <-- WK
```

Trong MVP, FastAPI hiện tại được giữ. BullMQ/NestJS không cần thêm chỉ vì đề bài gợi ý; dùng queue
hiện có hoặc một worker tương thích Redis để tránh tăng công nghệ trong tuần.

## 11. Ranh giới bảo mật bắt buộc

1. Authorization lọc resource trước khi nội dung vào model.
2. Tool registry chọn allowlist theo agent và policy; model không tự đặt tên endpoint tùy ý.
3. Raw message không vào audit/log/analytics; source ID có thể hash khi cần.
4. Prompt injection trong chat được xem là dữ liệu, không phải lệnh hệ thống.
5. Confirmation token gắn payload hash; chỉnh title/time/participants làm token cũ vô hiệu.
6. OAuth token mã hóa và thuộc từng user; platform admin không dùng token của user.
7. Consent revoke xóa/invalidate index/cache/memory liên quan theo retention policy.

## 12. Thứ tự triển khai hợp lý

`role/scope contract → policy decisions → role router → three prompt profiles → Employee vertical
slice → Manager Inbox → Executive aggregate brief → proactive → eval/hardening`.

Không merge/viết ba UI lớn trước khi chốt scope và policy, vì phần khó nhất không phải giao diện mà là
ngăn agent lấy sai dữ liệu. Kế hoạch triển khai và bản đồ coverage chỉ nên được nhập vào `main` sau
khi trạng thái test của các thành phần timeline, compaction và governed memory khớp với code thực tế.
