# Project Architecture Diagram

This document describes the architecture implemented by `Frontend/` and `src/`.
It intentionally separates working integrations from UI-only or planned parts.

## 1. System Context

```mermaid
flowchart LR
    Browser[Browser]

    subgraph Frontend[Frontend: React 18 + Vite]
        Router[React Router]
        AuthContext[AuthContext + localStorage token]
        Pages[Pages and shared layout]
        RestClient[apiFetch REST client]
        SocketHook[useChatSocket]
    end

    subgraph Backend[Backend: FastAPI + Uvicorn]
        AuthAPI[Auth REST routes]
        ChatAPI[Chat REST routes]
        ChatWS[Chat WebSocket route]
        AgentAPI[Agent REST routes]
        Health[Health and status routes]
    end

    DB[(SQLite database)]
    LLM[OpenAI Chat Model]
    Calendar[Google Calendar API]
    Scheduler[APScheduler]

    Browser --> Router
    Router --> AuthContext
    Router --> Pages
    Pages --> RestClient
    Pages --> SocketHook
    RestClient -->|HTTP JSON| AuthAPI
    RestClient -->|HTTP JSON| ChatAPI
    SocketHook -->|WebSocket JSON| ChatWS
    RestClient -.->|No current FE caller| AgentAPI

    AuthAPI --> DB
    ChatAPI --> DB
    ChatAPI --> ChatWS
    ChatWS --> DB
    AgentAPI --> LLM
    AgentAPI --> Calendar
    AgentAPI --> Scheduler
    Backend --> Health
```

## 2. Frontend Architecture

```mermaid
flowchart TB
    Entry[main.jsx]
    Entry --> Bootstrap[Bootstrap CSS and icons]
    Entry --> AuthProvider[AuthProvider]
    AuthProvider --> AppRouter[AppRouter]

    AppRouter --> Public[Public routes: /login, /register]
    AppRouter --> Guard[ProtectedRoute]
    Guard --> Layout[AppLayout]
    Layout --> Chat[ChatPage]
    Layout --> Assistant[PersonalAssistantPage]
    Layout --> Tasks[TaskPage]
    Layout --> Calendar[CalendarPage]
    Layout --> Reminders[ReminderPage]
    Layout --> Memory[MemoryPage]
    Layout --> Profile[ProfilePage]

    AuthProvider --> AuthAPIClient[api/auth.js]
    Chat --> ChatHooks[useConversations + useMessages]
    Chat --> ChatAPIClient[api/chat.js]
    Chat --> WebSocketClient[api/useWebSocket.js]
    ChatHooks --> ChatAPIClient
    ChatAPIClient --> Client[api/client.js]
    AuthAPIClient --> Client

    Assistant -.-> MockAssistant[Local component state and mock response]
    Tasks -.-> MockTasks[Hard-coded task data]
    Calendar -.-> MockCalendar[calendarEvents import; file currently missing]
    Reminders -.-> MockReminders[Local seed state]
    Memory -.-> MockMemory[Hard-coded memory data]
    Profile -.-> MockProfile[Local form state]
```

### Frontend integration status

| Area | Current implementation | Backend connection |
| --- | --- | --- |
| Login and registration | `AuthContext` calls `api/auth.js` | Connected to `/api/v1/auth/*` |
| User session | Bearer token stored as `orbit_token` | Connected to `/api/v1/auth/me` |
| Conversations | REST list/create/read plus WebSocket messages | Connected |
| Chat history | `useMessages` loads REST history | Connected |
| Personal Assistant | Local React state and placeholder reply | Not connected to `/api/v1/chat` |
| Tasks, Calendar, Reminders, Memory, Profile | Mock or local UI state | No corresponding FE API client |

## 3. Backend Modules

```mermaid
flowchart TB
    Main[src/main.py]
    Main --> Lifespan[Lifespan: init DB, start scheduler]
    Main --> CORS[CORS middleware]
    Main --> AuthRoutes[src/api/auth_routes.py]
    Main --> ChatRoutes[src/api/chat_routes.py]
    Main --> AgentRoutes[src/api/routes.py]
    Main --> WebSocketRoutes[src/websocket/routes.py]

    AuthRoutes --> AuthDeps[src/auth/dependencies.py]
    AuthRoutes --> Security[src/auth/security.py]
    ChatRoutes --> AuthDeps
    WebSocketRoutes --> Security
    ChatRoutes --> ChatService[src/services/chat_service.py]
    WebSocketRoutes --> ChatService

    AuthDeps --> Session[src/db/session.py]
    ChatRoutes --> Session
    ChatService --> Models[src/db/models.py]
    Session --> Models
    Models --> SQLite[(SQLite: users, conversations, participants, messages)]

    AgentRoutes --> Graph[src/agents/graph.py]
    Graph --> Planner[src/agents/nodes/planner_node.py]
    Graph --> ToolNode[LangGraph ToolNode]
    Planner --> LLMService[src/services/llm.py]
    LLMService --> OpenAI[OpenAI API]
    ToolNode --> Summarize[summarize_conversation]
    ToolNode --> CalendarTools[Google Calendar tools]
    ToolNode --> ReminderTools[Reminder tools]
    CalendarTools --> Google[Google Calendar API]
    ReminderTools --> Scheduler
    Graph --> MemorySaver[LangGraph MemorySaver: in process]
```

## 4. API and Message Flows

### Authentication

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as React AuthContext
    participant A as FastAPI auth routes
    participant D as SQLite

    B->>F: Submit email and password
    F->>A: POST /api/v1/auth/login or register
    A->>D: Read or create User
    A-->>F: JWT access_token and public user
    F->>F: Store token in localStorage
    F->>A: GET /api/v1/auth/me with Bearer token
    A->>D: Load current user
    A-->>F: User profile
```

### Real-time chat

```mermaid
sequenceDiagram
    participant F as ChatPage
    participant W as WebSocket /api/v1/ws
    participant S as Chat service
    participant D as SQLite
    participant M as ConnectionManager
    participant P as Other connected clients

    F->>W: Connect with JWT query token
    W->>W: Decode JWT and validate User
    W-->>F: WebSocket accepted
    F->>W: send_message(conversation_id, content)
    W->>S: Check participant and create message
    S->>D: Insert Message and update Conversation
    W->>M: Broadcast new_message
    M-->>F: new_message event
    M-->>P: new_message event
    F->>S: GET message history over REST when conversation changes
```

### AI agent flow

```mermaid
flowchart LR
    Request[POST /api/v1/chat] --> Build[Build LangGraph input and thread_id]
    Build --> Planner[Planner node]
    Planner -->|tool call| Tools[ToolNode]
    Tools --> Planner
    Planner -->|final AI message| Response[ChatResponse]
    Tools -->|calendar/reminder action| Interrupt[Human confirmation interrupt]
    Interrupt --> Resume[POST /api/v1/chat/resume]
    Resume --> Tools
    Planner --> OpenAI[OpenAI Chat Model]
    Tools --> Google[Google Calendar]
    Tools --> JobStore[In-memory reminder store + APScheduler]
```

## 5. Runtime and Persistence

```mermaid
flowchart LR
    Compose[docker-compose.yml] --> BackendContainer[Backend container: port 8000]
    BackendContainer --> DataVolume[data/ volume]
    DataVolume --> SQLite[(data/app.db)]
    BackendContainer --> Secrets[secrets/credentials.json and token.json]
    BrowserDev[Frontend Vite dev server: port 5173] --> BackendContainer
```

- The Docker Compose file runs the backend only. The frontend is run separately with Vite.
- The default database is SQLite at `./data/app.db`; database tables are created at startup.
- There is no Alembic migration setup in the current runtime.
- LangGraph uses `MemorySaver`, so agent thread checkpoints are lost on process restart.
- Reminders are held in module-level memory and scheduled by APScheduler; they are lost on restart and do not currently push a notification through WebSocket.
- Chroma is present only as configuration; no vector store is wired into the active graph.

## 6. Findings and Gaps

1. `Frontend/src/pages/CalendarPage.jsx` imports `Frontend/src/data/mockData`, but that module is absent, so the frontend build currently fails before runtime.
2. `PersonalAssistantPage` does not call the agent REST endpoints. The visible assistant response is a placeholder generated in `PersonalAIChat.jsx`.
3. The agent endpoints in `src/api/routes.py` do not depend on `get_current_user`; unlike chat and auth-me routes, they are not protected by JWT at the route layer.
4. The WebSocket authenticates with a JWT in the URL query string. This works with the current client but exposes tokens to URL-level logging unless deployment logging is controlled.
5. `@orbit` is presented as a UI hint in the chat composer, but the WebSocket handler currently treats every `send_message` as a normal persisted chat message and does not invoke the AI agent.
