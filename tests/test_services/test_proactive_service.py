from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.db import session as db_session
from src.db.models import Task
from src.services import proactive_service


@pytest.mark.parametrize(
    "text,expected",
    [
        ("let's meet tomorrow at 3pm", True),
        ("don't forget the deadline is Friday", True),
        ("họp lúc 9 giờ sáng mai nhé", True),
        ("haha nice one", False),
        ("thanks!", False),
    ],
)
def test_looks_like_commitment(text, expected):
    assert proactive_service._looks_like_commitment(text) is expected


@pytest.mark.asyncio
async def test_maybe_suggest_task_skips_llm_when_no_signal(monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    await proactive_service.maybe_suggest_task(conversation_id="c1", sender_id="u1", content="thanks!")

    fake_llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_suggest_task_creates_suggested_task(client, auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(
        content='{"has_commitment": true, "title": "Gửi báo cáo", "due_at": "2026-08-10T09:00:00"}'
    )
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    await proactive_service.maybe_suggest_task(
        conversation_id="c1", sender_id="u1", content="đừng quên deadline gửi báo cáo thứ hai nhé"
    )

    async with db_session.async_session_maker() as db:
        tasks = (await db.execute(select(Task).where(Task.owner_id == "u1"))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "Gửi báo cáo"
    assert tasks[0].source == "proactive"
    assert tasks[0].status == "suggested"


@pytest.mark.asyncio
async def test_maybe_suggest_task_no_op_when_llm_says_no_commitment(client, auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(content='{"has_commitment": false}')
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    await proactive_service.maybe_suggest_task(
        conversation_id="c1", sender_id="u2", content="meeting tomorrow, just kidding"
    )

    async with db_session.async_session_maker() as db:
        tasks = (await db.execute(select(Task).where(Task.owner_id == "u2"))).scalars().all()
    assert tasks == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_never_raises_on_llm_error(monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.side_effect = RuntimeError("boom")
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    await proactive_service.maybe_suggest_task(conversation_id="c1", sender_id="u1", content="meeting tomorrow")
