from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.db.base import Base
from src.db.session import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Async HTTP client for testing API endpoints, backed by an isolated in-memory test DB."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with test_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # The websocket handler can't use FastAPI's per-request Depends() (it needs a fresh
    # session per inbound frame over one long-lived connection), so it reads the module-level
    # session maker directly - patch that too so websocket tests hit the same in-memory DB.
    monkeypatch.setattr("src.db.session.async_session_maker", test_session_maker)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def auth_headers(client):
    """Registers a test user and returns an Authorization header for it."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "password123", "display_name": "Alice"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_auth_headers(client):
    """Registers a second test user and returns an Authorization header for it."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "password123", "display_name": "Bob"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock


class FakeToolCallingLLM:
    """Stand-in for a ChatOpenAI instance bound to tools.

    `.bind_tools(...)` returns self (mirroring the real API), and each `.ainvoke(...)`
    call pops the next scripted response off a queue - lets a test script an exact
    AIMessage(tool_calls=[...]) -> AIMessage(content=...) sequence without a live LLM.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            raise AssertionError("FakeToolCallingLLM ran out of scripted responses")
        return self._responses.pop(0)


@pytest.fixture
def fake_llm_factory():
    def _make(responses: list) -> FakeToolCallingLLM:
        return FakeToolCallingLLM(responses)

    return _make
