# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

P-132 is a team project for the **VinUni AI20K Build Phase**, built from the AI20K Agent Template. The goal (see [Frontend/detai.md](Frontend/detai.md)) is an AI agent embedded in a chat app that summarizes conversations, extracts tasks/appointments, creates reminders (with human-in-the-loop confirmation), and manages a personal calendar.

The repo currently has two largely disconnected halves:
- **Backend** (`src/`): a FastAPI + LangGraph agent with real tool-calling (summarize / Google Calendar / reminders) and human-in-the-loop confirmation via LangGraph interrupts. No DB wiring yet.
- **Frontend** (`Frontend/`): a separate React + Vite SPA (`orbit-ai-assistant`) that is UI-complete but runs entirely on mock data — no API calls, no real auth. See [Frontend/README.md](Frontend/README.md).

There is no integration between them yet — connecting the frontend to real backend endpoints is unbuilt work, not an existing pattern to follow.

## Backend (`src/`) — FastAPI + LangGraph

Commands (run from repo root, Python 3.11+, venv at `.venv`):
```bash
make run     # uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
make test    # pytest tests/ -v
make lint    # ruff check src/ tests/
make format  # ruff format src/ tests/
make check   # lint + format + test
```
Swagger UI at `http://localhost:8000/docs`. Config comes from `.env` (copy from `.env.example`) loaded via `src/config.py::Settings` (pydantic-settings).

Architecture — `planner` (LLM bound to tools) ⇄ `tools` (`ToolNode`) loop, compiled with a `MemorySaver` checkpointer:
- `src/agents/state.py` — `AgentState` TypedDict (`total=False`); `messages` uses the `add_messages` reducer, plus flat fields (`context`, `summary`, `error`, ...).
- `src/agents/graph.py::build_graph()` — `agent` (module-level, reused across requests) routes `planner → tools_condition → {tools|END}`, `tools → planner`. A checkpointer is attached, so `agent.ainvoke(...)` **requires** `config={"configurable": {"thread_id": ...}}`.
- `src/agents/nodes/planner_node.py` — the real planner node (`get_llm().bind_tools(ALL_TOOLS)`). `example_node.py` is old placeholder scaffolding, not wired into the graph.
- `src/agents/tools/` — `summarize_tool.py` (reads `state["context"]` via `InjectedState`, no confirmation needed), `calendar_tool.py` (real Google Calendar API), `reminder_tool.py` (APScheduler-backed). Calendar/reminder creation call `interrupt({"type": ..., "draft": ...})` before committing — see `src/api/routes.py`'s `/chat/resume` for the resume side. `tools/__init__.py::ALL_TOOLS` is the registry bound to the LLM; `example_tool.py` stays unwired reference code.
- `src/services/llm.py::get_llm()` — `ChatOpenAI` client from settings (OpenAI only). `src/services/scheduler.py` — module-level APScheduler `AsyncIOScheduler`, started/stopped in `main.py`'s `lifespan`.
- `src/api/routes.py` — `POST /chat` (accepts `message`, optional `messages` for summarize context, optional `thread_id`) and `POST /chat/resume` (`{thread_id, approved, edits}`) on one `APIRouter`, mounted at `/api/v1`.
- Google Calendar needs a one-time `python scripts/google_oauth_setup.py` locally to produce `secrets/token.json` (gitignored) from `secrets/credentials.json`.
- Database/vector store still unwired: SQLAlchemy/psycopg2/chromadb stay commented out in `requirements.txt`; `database_url`/`chroma_persist_dir` settings have no consumers. Reminders/scheduled jobs are in-memory only (lost on restart).

Testing: `tests/conftest.py`'s `client` fixture (httpx `ASGITransport`) and `fake_llm_factory` (a `.bind_tools()`-aware fake LLM that returns scripted `AIMessage`s — use this instead of the old unused `mock_llm` for anything touching the planner/tools). `tests/test_agents/test_tools/` covers each tool; interrupt→resume round trips are driven through the full compiled `agent` with a fixed `thread_id`.

Linting: ruff only (`ruff.toml`: line-length 120, double quotes, `E501` ignored). `make typecheck`/mypy is in the Makefile but mypy isn't in `requirements.txt` — don't rely on it being installed.

## Frontend (`Frontend/`) — React + Vite

```bash
cd Frontend
npm install
npm run dev       # http://localhost:5173
npm run build
npm run preview
```
No lint/test scripts are configured.

Architecture:
- `src/router/AppRouter.jsx` — all routes; `/` redirects to `/assistant`. `/login` and `/register` are standalone; every other route is nested under `AppLayout` (sidebar + top navbar shell).
- `src/pages/` — one component per route.
- `src/components/<feature>/` — components grouped by feature area (`chat/`, `calendar/`, `task/`, `ai/`, `layout/`, `common/`, `profile/`).
- `src/data/mockData.js` — the only data source right now (`tasks`, `calendarEvents`, `conversations`, `messages`). Pages import directly from this file; when wiring real APIs, replace these imports rather than adding a parallel data path.
- Styling is plain CSS (`src/styles.css`, `src/assistant.css`) plus Bootstrap 5 — no CSS-in-JS or Tailwind despite Tailwind being mentioned in the top-level README's suggested stack.
- JSX in this codebase is written densely (minimal line breaks, inline ternaries for conditional classes) — match the existing style rather than reformatting to one-JSX-element-per-line.

## Cross-cutting: AI usage logging (graded requirement)

This is an AI20K coursework repo — AI tool usage is auto-logged and factors into grading (README.md deliverable #4). `.claude/settings.json` configures Claude Code hooks that log prompts; a pre-push git hook (installed via `scripts/setup_hooks.sh` / `scripts/setup_hooks.ps1`) submits `.ai-log/session.jsonl` on `git push`. Don't remove or bypass these hooks, and don't add `--no-verify` to pushes in this repo.

## Docs that reflect team process, not just code

- `WORKLOG.md` — daily log table (Member | Task | Status | Output | Time), append rather than rewrite.
- `ARCHITECTURE.md` — currently unfilled template placeholders; treat as a document to complete, not a source of truth about the current design.
- `docs/guide/` — the full AI20K course guidebook (setup, LangGraph, FastAPI, testing, deployment chapters) — check here before inventing conventions from scratch.
