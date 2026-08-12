from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.agents.graph import close_checkpointer, init_checkpointer
from src.api.admin_routes import router as admin_router
from src.api.auth_routes import router as auth_router
from src.api.calendar_routes import router as calendar_router
from src.api.chat_routes import router as chat_router
from src.api.memory_routes import router as memory_router
from src.api.rate_limit import limiter
from src.api.reminder_routes import router as reminder_router
from src.api.routes import router
from src.api.task_routes import router as task_router
from src.config import get_settings
from src.db.session import init_db
from src.services import calendar_service
from src.services.scheduler import scheduler
from src.websocket.routes import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    await init_db()
    await init_checkpointer()
    scheduler.start()
    scheduler.add_job(
        calendar_service.poll_calendar_changes,
        "interval",
        seconds=settings.calendar_poll_interval_seconds,
        id="calendar_poll",
        replace_existing=True,
    )
    yield
    scheduler.shutdown(wait=False)
    await close_checkpointer()
    print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (slowapi) - see src/api/rate_limit.py. Routes opt in individually via
# @limiter.limit(...); anything undecorated (e.g. /health, /chat/resume) is never limited.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
app.include_router(ws_router, prefix="/api/v1", tags=["ws"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(task_router, prefix="/api/v1", tags=["tasks"])
app.include_router(calendar_router, prefix="/api/v1", tags=["calendar"])
app.include_router(reminder_router, prefix="/api/v1", tags=["reminders"])
app.include_router(memory_router, prefix="/api/v1", tags=["memory"])


@app.get("/health")
@limiter.exempt
async def health():
    return {"status": "ok", "env": settings.app_env}
