import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import Task
from src.services import chat_service, proactive_service


@pytest.mark.parametrize(
    "raw,expected",
    [
        (json.dumps({"relevant": True}), True),
        (json.dumps({"relevant": False}), False),
        ("```json\n" + json.dumps({"relevant": False}) + "\n```", False),  # fenced, still parses
        ("not json at all", True),  # unparseable -> fail open
        (json.dumps({"unexpected": "shape"}), True),  # well-formed JSON but no "relevant" key -> fail open
        (json.dumps(["relevant", True]), True),  # valid JSON but not a dict -> fail open
        (123, True),  # non-string content (e.g. a Mock the test forgot to configure) -> fail open
    ],
)
def test_parse_relevant(raw, expected):
    assert proactive_service._parse_relevant(raw) is expected


@pytest.mark.parametrize(
    "title,owner_name,expected",
    [
        ("Tiệc sinh nhật của Tấn lúc 9 giờ sáng mai", "Tấn", "Tiệc sinh nhật của tôi lúc 9 giờ sáng mai"),
        ("Tấn mời mọi người đi ăn", "Tấn", "tôi mời mọi người đi ăn"),
        ("Họp nhóm", "Tấn", "Họp nhóm"),  # name doesn't appear - unchanged
        ("Tiệc sinh nhật của Tấn", "", "Tiệc sinh nhật của Tấn"),  # no owner name known - unchanged
        ("Đội trưởng Andy đến họp", "An", "Đội trưởng Andy đến họp"),  # "An" is only a substring of "Andy" - word boundary blocks it
    ],
)
def test_personalize_title(title, owner_name, expected):
    assert proactive_service._personalize_title(title, owner_name) == expected


async def _user_id(client, headers):
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _create_conversation(client, creator_headers, other_headers):
    other_id = await _user_id(client, other_headers)
    conv = await client.post(
        "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=creator_headers
    )
    return conv.json()["id"]


async def _create_group(client, creator_headers, *other_headers_list, name="Nhóm"):
    other_ids = [await _user_id(client, h) for h in other_headers_list]
    conv = await client.post(
        "/api/v1/conversations",
        json={"type": "group", "name": name, "participant_ids": other_ids},
        headers=creator_headers,
    )
    return conv.json()["id"]


async def _register(client, *, email, display_name):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123", "display_name": display_name}
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def _grant_ai_permission(client, conversation_id, headers):
    await client.put(f"/api/v1/conversations/{conversation_id}/ai-permission", json={"granted": True}, headers=headers)


async def _grant_all(client, conversation_id, *headers_list):
    """Grant AI permission for every participant listed - the default for most tests, since
    _load_window only shows the LLM messages from senders who have granted. Tests that
    specifically exercise the permission boundary (D1) deliberately skip a participant instead."""
    for headers in headers_list:
        await _grant_ai_permission(client, conversation_id, headers)


def _llm_response(commitments: list[dict]) -> AsyncMock:
    # usage_metadata=None explicitly - otherwise AsyncMock auto-generates a mock attribute for it,
    # which usage_service.log_usage then tries to call .get(...) on, producing a coroutine instead
    # of a value and a noisy (harmless, self-caught) "Failed to log LLM usage" log on every call.
    return AsyncMock(content=json.dumps({"commitments": commitments}), usage_metadata=None)


def _relevant_response(relevant: bool = True) -> AsyncMock:
    """Response for the cheap relevance pass (pass 1) - every maybe_suggest_task call now does
    this call FIRST, then (if relevant) the windowed extraction call _llm_response builds for.
    Tests that only care about pass 2 use side_effect=[_relevant_response(), _llm_response(...)]."""
    return AsyncMock(content=json.dumps({"relevant": relevant}), usage_metadata=None)


async def _tasks_for(owner_id):
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(Task).where(Task.owner_id == owner_id))).scalars().all()


# ---------------------------------------------------------------- maybe_suggest_task: main flow


@pytest.mark.asyncio
async def test_maybe_suggest_task_confirmation_creates_task_for_confirmer(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """1-1: A đề xuất, B "ok" -> B có task, source_message_id = id tin đề xuất của A."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        proposal = await chat_service.create_message(db, conversation_id, proposer_id, "Tối nay 8 giờ đi ăn tối nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Đi ăn tối",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Bob", "evidence": "confirmed", "message_index": 2}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    tasks = await _tasks_for(confirmer_id)
    assert len(tasks) == 1
    assert tasks[0].source == "proactive"
    assert tasks[0].status == "suggested"
    assert tasks[0].source_message_id == proposal.id


@pytest.mark.asyncio
async def test_maybe_suggest_task_invited_creates_task_for_invitee_without_reply(client, monkeypatch):
    """Quỳnh mời Tuấn ăn tối - Tuấn CHƯA trả lời gì cả, vẫn phải có task cho cả hai: Quỳnh (self)
    và Tuấn (invited). Đúng kịch bản người dùng yêu cầu thêm tính năng này."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    quynh_headers, quynh_id = await _register(client, email="quynh@example.com", display_name="Quỳnh")
    tuan_headers, tuan_id = await _register(client, email="tuan@example.com", display_name="Tuấn")
    conversation_id = await _create_conversation(client, quynh_headers, tuan_headers)
    await _grant_all(client, conversation_id, quynh_headers, tuan_headers)

    async with db_session.async_session_maker() as db:
        invite = await chat_service.create_message(
            db, conversation_id, quynh_id, "tối nay mời Tuấn ăn tối lúc 8 giờ nhé"
        )

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Ăn tối cùng Quỳnh",
                    "due_at": "2026-08-15T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [
                        {"name": "Quỳnh", "evidence": "self", "message_index": 1},
                        {"name": "Tuấn", "evidence": "invited", "message_index": 1},
                    ],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=quynh_id, content="tối nay mời Tuấn ăn tối lúc 8 giờ nhé"
    )

    quynh_tasks = await _tasks_for(quynh_id)
    assert len(quynh_tasks) == 1
    assert quynh_tasks[0].title == "Ăn tối cùng tôi"  # her own name in the title -> personalized to "tôi"
    assert quynh_tasks[0].source_message_id == invite.id

    tuan_tasks = await _tasks_for(tuan_id)
    assert len(tuan_tasks) == 1
    assert tuan_tasks[0].source == "proactive"
    assert tuan_tasks[0].status == "suggested"
    assert tuan_tasks[0].source_message_id == invite.id
    assert tuan_tasks[0].title == "Ăn tối cùng Quỳnh (lời mời từ Quỳnh, chưa xác nhận)"


@pytest.mark.asyncio
async def test_maybe_suggest_task_invited_unnamed_in_1on1_conversation(client, monkeypatch):
    """★ Đúng bug người dùng gặp thật: "sáng mai 8 giờ đi ăn sáng nhé" trong 1-1, KHÔNG hề nêu tên
    Tuấn - vẫn phải tạo task cho Tuấn vì trong hội thoại 1-1 chỉ có đúng 2 người, không thể là đề
    xuất cho ai khác. is_direct=True truyền vào _build_window_prompt phải phản ánh đúng việc này -
    test verify qua prompt thật gửi cho LLM (không mock is_direct), không chỉ qua response giả."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    quynh_headers, quynh_id = await _register(client, email="quynh3@example.com", display_name="Quỳnh")
    tuan_headers, tuan_id = await _register(client, email="tuan3@example.com", display_name="Tuấn")
    conversation_id = await _create_conversation(client, quynh_headers, tuan_headers)
    await _grant_all(client, conversation_id, quynh_headers, tuan_headers)

    async with db_session.async_session_maker() as db:
        invite = await chat_service.create_message(db, conversation_id, quynh_id, "sáng mai 8 giờ đi ăn sáng nhé")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Ăn sáng cùng Quỳnh",
                    "due_at": "2026-08-16T08:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [
                        {"name": "Quỳnh", "evidence": "self", "message_index": 1},
                        {"name": "Tuấn", "evidence": "invited", "message_index": 1},
                    ],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=quynh_id, content="sáng mai 8 giờ đi ăn sáng nhé"
    )

    # The prompt actually told the LLM this is a 1-on-1 with exactly these two people - the thing
    # that makes an unnamed "invited" claim resolvable at all.
    window_prompt = fake_llm.ainvoke.await_args_list[1].args[0]
    assert "private 1-on-1 conversation between exactly these two people" in window_prompt
    assert "Quỳnh" in window_prompt and "Tuấn" in window_prompt

    tuan_tasks = await _tasks_for(tuan_id)
    assert len(tuan_tasks) == 1
    assert tuan_tasks[0].source_message_id == invite.id
    assert tuan_tasks[0].title == "Ăn sáng cùng Quỳnh (lời mời từ Quỳnh, chưa xác nhận)"


@pytest.mark.asyncio
async def test_maybe_suggest_task_group_conversation_is_not_treated_as_1on1(client, monkeypatch):
    """★ Regression: is_direct chỉ True khi hội thoại có ĐÚNG 2 người - nhóm ≥3 người dù chỉ 2
    người đã cấp quyền cũng không được coi là 1-1, tránh gợi ý sai người trong nhóm đông."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    quynh_headers, quynh_id = await _register(client, email="quynh4@example.com", display_name="Quỳnh")
    tuan_headers, _tuan_id = await _register(client, email="tuan4@example.com", display_name="Tuấn")
    # Deliberately not "Chi" - that name already appears in the prompt's own static few-shot
    # example, which would make a naive substring check below a false positive either way.
    dung_headers, _dung_id = await _register(client, email="dung4@example.com", display_name="Dung")
    conversation_id = await _create_group(client, quynh_headers, tuan_headers, dung_headers, name="Nhóm 3 người")
    await _grant_all(client, conversation_id, quynh_headers, tuan_headers)  # Dung never grants

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, quynh_id, "sáng mai 8 giờ đi ăn sáng nhé")

    fake_llm.ainvoke.side_effect = [_relevant_response(), _llm_response([])]

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=quynh_id, content="sáng mai 8 giờ đi ăn sáng nhé"
    )

    window_prompt = fake_llm.ainvoke.await_args_list[1].args[0]
    assert "private 1-on-1 conversation" not in window_prompt
    assert "Dung" not in window_prompt  # never granted - name must not leak even without her content


@pytest.mark.asyncio
async def test_maybe_suggest_task_invited_requires_invitee_own_permission(client, monkeypatch):
    """Quỳnh mời Tuấn, Quỳnh đã bật quyền AI (nên detection chạy được) nhưng Tuấn CHƯA tự bật quyền
    AI cho hội thoại này - Tuấn không được tạo task, dù được mời đích danh. Quyền riêng tư vẫn ưu
    tiên hơn tính năng "invited" mới: không thể tạo dữ liệu AI cho ai chưa tự đồng ý."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    quynh_headers, quynh_id = await _register(client, email="quynh2@example.com", display_name="Quỳnh")
    tuan_headers, tuan_id = await _register(client, email="tuan2@example.com", display_name="Tuấn")
    conversation_id = await _create_conversation(client, quynh_headers, tuan_headers)
    await _grant_ai_permission(client, conversation_id, quynh_headers)  # only Quỳnh grants - not Tuấn

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, quynh_id, "tối nay mời Tuấn ăn tối lúc 8 giờ nhé")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Ăn tối cùng Quỳnh",
                    "due_at": "2026-08-15T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [
                        {"name": "Quỳnh", "evidence": "self", "message_index": 1},
                        {"name": "Tuấn", "evidence": "invited", "message_index": 1},
                    ],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=quynh_id, content="tối nay mời Tuấn ăn tối lúc 8 giờ nhé"
    )

    assert len(await _tasks_for(quynh_id)) == 1  # Quỳnh still gets her own self-committed task
    assert await _tasks_for(tuan_id) == []  # Tuấn never granted his own permission - no task for him


@pytest.mark.asyncio
async def test_maybe_suggest_task_delegation_is_not_invited(client, auth_headers, other_auth_headers, monkeypatch):
    """★ Regression: giao việc một chiều ("Chi ơi mai 3h em gửi báo cáo nhé") không được vô tình
    biến thành "invited" chỉ vì có tên người khác trong tin nhắn - việc phân biệt "giao việc" khác
    "mời cùng làm gì đó" là trách nhiệm của prompt (đã có ví dụ few-shot riêng dạy LLM điều này);
    test này xác nhận khi LLM tuân đúng prompt và trả owners rỗng, không có task nào được tạo."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    chi_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "Chi ơi mai 3h em gửi báo cáo nhé")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response([{"title": "Gửi báo cáo", "due_at": None, "proposal_message_index": 1, "cancelled": False, "owners": []}]),
    ]

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=proposer_id, content="Chi ơi mai 3h em gửi báo cáo nhé"
    )

    assert await _tasks_for(chi_id) == []  # prompt taught the LLM this is delegation, not an invite -> no owners


def test_verify_owner_rejects_self_invite():
    """Cơ học thuần: 1 claim "invited" nhưng message_index trỏ vào chính tin của người được claim
    là owner (tự mời chính mình) - luôn bị từ chối, không phụ thuộc gì vào LLM."""
    fake_message = type("FakeMessage", (), {"sender_id": "user-1"})()
    fake_sender = type("FakeUser", (), {"id": "user-1", "display_name": "Ai"})()
    window = [(fake_message, fake_sender)]
    claim = {"name": "Ai", "evidence": "invited", "message_index": 1}

    result = proactive_service._verify_owner(
        claim, window=window, roster={"Ai": "user-1"}, granted_ids={"user-1"}, proposal_idx=1
    )

    assert result is None


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_owner_when_message_index_points_to_wrong_sender(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """★ C3: LLM claims owner "Bob" but message_index actually points at Carol's message - the
    sender-match check in _verify_owner must catch the lie regardless of the claimed name."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    carol_headers, carol_id = await _register(client, email="carol@example.com", display_name="Carol")
    proposer_id = await _user_id(client, auth_headers)
    bob_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_group(client, auth_headers, other_auth_headers, carol_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers, carol_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay đi ăn nhé")
        await chat_service.create_message(db, conversation_id, carol_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Đi ăn tối",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    # message_index 2 was actually sent by Carol, not Bob.
                    "owners": [{"name": "Bob", "evidence": "confirmed", "message_index": 2}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=carol_id, content="ok")

    assert await _tasks_for(bob_id) == []
    assert await _tasks_for(carol_id) == []  # claimed name was "Bob", not Carol - no fallback guess either


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_owner_when_confirmation_message_sent_by_someone_else(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """★ C3 variant: owner claimed as "Chi" but the cited message was sent by Bob - "B ok hộ Chi"
    must never count as Chi's own evidence."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    chi_headers, chi_id = await _register(client, email="chi@example.com", display_name="Chi")
    proposer_id = await _user_id(client, auth_headers)
    bob_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_group(client, auth_headers, other_auth_headers, chi_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers, chi_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "Chi ơi mai 3h em gửi báo cáo nhé")
        await chat_service.create_message(db, conversation_id, bob_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Gửi báo cáo",
                    "due_at": "2026-08-12T15:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Chi", "evidence": "confirmed", "message_index": 2}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=chi_id, content="ok")

    assert await _tasks_for(chi_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_owner_name_not_in_roster(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Zzz Không Tồn Tại", "evidence": "self", "message_index": 1}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(proposer_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_when_display_name_is_ambiguous(client, auth_headers, other_auth_headers, monkeypatch):
    """Hai thành viên cùng display_name "Alice" - roster loại cả 2, không ai nhận được task dù
    message_index/sender khớp thật, vì không cách nào phân giải an toàn tên nào ứng với ai."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    twin_headers, twin_id = await _register(client, email="alice2@example.com", display_name="Alice")
    alice_id = await _user_id(client, auth_headers)
    conversation_id = await _create_group(client, auth_headers, twin_headers, name="Trùng tên")
    await _grant_all(client, conversation_id, auth_headers, twin_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, alice_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, twin_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Alice", "evidence": "confirmed", "message_index": 2}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=twin_id, content="ok")

    assert await _tasks_for(alice_id) == []
    assert await _tasks_for(twin_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_confirmed_evidence_not_after_proposal(
    client, auth_headers, other_auth_headers, monkeypatch
):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    # "confirmed" but pointing at the proposal message itself (index <= proposal_idx).
                    "owners": [{"name": "Alice", "evidence": "confirmed", "message_index": 1}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(proposer_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_unknown_evidence_value(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Bob", "evidence": "assigned", "message_index": 2}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(confirmer_id) == []


def test_verify_owner_rejects_when_owner_has_not_granted_permission():
    """★ bảo mật: unit test trực tiếp _verify_owner (không qua maybe_suggest_task) - trong pipeline
    thật, _load_window đã tự loại tin của người chưa cấp quyền nên trường hợp này không thể phát
    sinh qua toàn luồng; test này bảo vệ tầng phòng thủ độc lập trong _verify_owner, phòng khi
    _load_window đổi hành vi sau này mà quên đồng bộ."""

    class _Msg:
        sender_id = "bob-id"
        content = "8 giờ tối nay họp nhé"

    class _User:
        display_name = "Bob"

    window = [(_Msg(), _User())]
    claim = {"name": "Bob", "evidence": "self", "message_index": 1}

    result = proactive_service._verify_owner(
        claim, window=window, roster={"Bob": "bob-id"}, granted_ids=set(), proposal_idx=1
    )
    assert result is None


@pytest.mark.asyncio
async def test_maybe_suggest_task_prompt_excludes_messages_from_non_granted_participants(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """★ D1: nội dung tin nhắn của người CHƯA cấp quyền AI không được xuất hiện trong prompt gửi
    ra LLM, kể cả khi tin đó có tín hiệu lịch trình rõ ràng."""
    fake_llm = AsyncMock()
    fake_llm.ainvoke.side_effect = [_relevant_response(), _llm_response([])]
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    carol_headers, carol_id = await _register(client, email="ungranted@example.com", display_name="Carol")
    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_group(client, auth_headers, other_auth_headers, carol_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)
    # Carol never grants - her message must stay invisible to the LLM.

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, carol_id, "3 giờ chiều nay tôi họp riêng")
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay đi ăn tối nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    prompt_sent = fake_llm.ainvoke.await_args.args[0]
    assert "3 giờ chiều nay tôi họp riêng" not in prompt_sent
    assert "8 giờ tối nay đi ăn tối nhé" in prompt_sent
    assert "] Bob" in prompt_sent  # confirmer's "ok" line is present


@pytest.mark.asyncio
async def test_maybe_suggest_task_rejects_out_of_range_message_index(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Bob", "evidence": "confirmed", "message_index": 999}],
                }
            ]
        ),
    ]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(confirmer_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_is_idempotent_on_overlapping_windows(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    response = _llm_response(
        [
            {
                "title": "Họp",
                "due_at": "2026-08-11T20:00:00",
                "proposal_message_index": 1,
                "cancelled": False,
                "owners": [{"name": "Bob", "evidence": "confirmed", "message_index": 2}],
            }
        ]
    )
    # 2 maybe_suggest_task calls x 2 LLM passes (relevance, then extraction) each = 4 responses.
    fake_llm.ainvoke.side_effect = [_relevant_response(), response, _relevant_response(), response]

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert len(await _tasks_for(confirmer_id)) == 1


@pytest.mark.asyncio
async def test_maybe_suggest_task_cancelled_retracts_suggested_task(client, auth_headers, other_auth_headers, monkeypatch):
    """★ E1: đề xuất bị huỷ -> Task còn "suggested" sinh ra từ nó chuyển "dismissed"."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")
        await chat_service.create_message(db, conversation_id, confirmer_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Bob", "evidence": "confirmed", "message_index": 2}],
                }
            ]
        ),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")
    tasks = await _tasks_for(confirmer_id)
    assert tasks[0].status == "suggested"

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "thôi huỷ nhé")

    broadcasts = []
    monkeypatch.setattr(
        proactive_service.manager,
        "broadcast_to_users",
        AsyncMock(side_effect=lambda ids, payload: broadcasts.append((ids, payload))),
    )
    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response([{"proposal_message_index": 1, "cancelled": True, "owners": []}]),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=proposer_id, content="thôi huỷ nhé")

    tasks = await _tasks_for(confirmer_id)
    assert len(tasks) == 1
    assert tasks[0].status == "dismissed"
    assert any(payload["type"] == "task_updated" and confirmer_id in ids for ids, payload in broadcasts)


@pytest.mark.asyncio
async def test_maybe_suggest_task_renegotiation_keeps_only_final_time(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """★ F1: A "8h nhé" -> B "9h được không" -> A "ok" phải chỉ còn 1 task active ở giờ cuối, task
    8h ban đầu bị rút lại (dismissed), không phải 2 task chồng lên nhau."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    a_id = await _user_id(client, auth_headers)
    b_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, a_id, "8h nhé")
    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [{"name": "Alice", "evidence": "self", "message_index": 1}],
                }
            ]
        ),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=a_id, content="8h nhé")

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, b_id, "9h được không")
        await chat_service.create_message(db, conversation_id, a_id, "ok")
    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {"proposal_message_index": 1, "cancelled": True, "owners": []},
                {
                    "title": "Họp",
                    "due_at": "2026-08-11T21:00:00",
                    "proposal_message_index": 2,
                    "cancelled": False,
                    "owners": [{"name": "Alice", "evidence": "confirmed", "message_index": 3}],
                },
            ]
        ),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=a_id, content="ok")

    tasks = await _tasks_for(a_id)
    active = [t for t in tasks if t.status == "suggested"]
    assert len(active) == 1
    # due_at comes back UTC from the DB - convert to local before checking the wall-clock hour.
    tz = ZoneInfo(get_settings().calendar_timezone)
    assert active[0].due_at.astimezone(tz).hour == 21
    assert any(t.status == "dismissed" for t in tasks)


@pytest.mark.asyncio
async def test_maybe_suggest_task_group_multiple_confirmers_in_one_pass(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """Nhóm 3 người: B và C cùng "ok" -> 2 task, mỗi người 1, xử lý trong đúng 1 lệnh gọi LLM."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    carol_headers, carol_id = await _register(client, email="carol2@example.com", display_name="Carol")
    a_id = await _user_id(client, auth_headers)
    b_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_group(client, auth_headers, other_auth_headers, carol_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers, carol_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, a_id, "8 giờ tối nay đi ăn nhé")
        await chat_service.create_message(db, conversation_id, b_id, "ok")
        await chat_service.create_message(db, conversation_id, carol_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Đi ăn tối",
                    "due_at": "2026-08-11T20:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [
                        {"name": "Bob", "evidence": "confirmed", "message_index": 2},
                        {"name": "Carol", "evidence": "confirmed", "message_index": 3},
                    ],
                }
            ]
        ),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=carol_id, content="ok")

    # 1 relevance pass + 1 windowed extraction pass for this single message - not 1 per owner found.
    assert fake_llm.ainvoke.await_count == 2
    assert len(await _tasks_for(b_id)) == 1
    assert len(await _tasks_for(carol_id)) == 1


@pytest.mark.asyncio
async def test_maybe_suggest_task_personalizes_title_per_owner(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """A đề xuất tiệc sinh nhật của chính mình, B xác nhận tham gia - task của A (chủ tiệc) phải
    đọc "của tôi", còn task của B (khách mời, task riêng của B) vẫn giữ "của Alice" như LLM viết."""
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    alice_id = await _user_id(client, auth_headers)
    bob_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, alice_id, "sáng mai 9h tới tiệc sinh nhật của tôi nhé")
        await chat_service.create_message(db, conversation_id, bob_id, "ok")

    fake_llm.ainvoke.side_effect = [
        _relevant_response(),
        _llm_response(
            [
                {
                    "title": "Tiệc sinh nhật của Alice",
                    "due_at": "2026-08-11T09:00:00",
                    "proposal_message_index": 1,
                    "cancelled": False,
                    "owners": [
                        {"name": "Alice", "evidence": "self", "message_index": 1},
                        {"name": "Bob", "evidence": "confirmed", "message_index": 2},
                    ],
                }
            ]
        ),
    ]
    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=bob_id, content="ok")

    alice_tasks = await _tasks_for(alice_id)
    bob_tasks = await _tasks_for(bob_id)
    assert alice_tasks[0].title == "Tiệc sinh nhật của tôi"
    assert bob_tasks[0].title == "Tiệc sinh nhật của Alice"


@pytest.mark.asyncio
async def test_load_window_excludes_messages_older_than_max_age(client, auth_headers, other_auth_headers):
    """D4: tin cũ hơn _WINDOW_MAX_AGE (6 giờ) bị loại khỏi cửa sổ."""
    sender_id = await _user_id(client, auth_headers)
    other_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        old = await chat_service.create_message(db, conversation_id, sender_id, "tin rất cũ")
        old.created_at = datetime.now(UTC) - timedelta(hours=7)
        await db.commit()
        await chat_service.create_message(db, conversation_id, other_id, "tin mới")

        window, _roster, _granted, _is_direct = await proactive_service._load_window(db, conversation_id=conversation_id)

    assert [m.content for m, _ in window] == ["tin mới"]


@pytest.mark.asyncio
async def test_load_window_caps_message_count(client, auth_headers, other_auth_headers):
    """B6: cửa sổ giới hạn _WINDOW_MAX_MESSAGES tin, giữ lại các tin MỚI NHẤT."""
    sender_id = await _user_id(client, auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_ai_permission(client, conversation_id, auth_headers)

    async with db_session.async_session_maker() as db:
        for i in range(proactive_service._WINDOW_MAX_MESSAGES + 5):
            await chat_service.create_message(db, conversation_id, sender_id, f"tin {i}")

        window, _roster, _granted, _is_direct = await proactive_service._load_window(db, conversation_id=conversation_id)

    assert len(window) == proactive_service._WINDOW_MAX_MESSAGES
    assert window[-1][0].content == f"tin {proactive_service._WINDOW_MAX_MESSAGES + 4}"


@pytest.mark.asyncio
async def test_maybe_suggest_task_invalid_json_does_not_raise(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(content="not json at all", usage_metadata=None)
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(confirmer_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_missing_commitments_key_does_not_raise(
    client, auth_headers, other_auth_headers, monkeypatch
):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(content=json.dumps({"unexpected": "shape"}), usage_metadata=None)
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    proposer_id = await _user_id(client, auth_headers)
    confirmer_id = await _user_id(client, other_auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_all(client, conversation_id, auth_headers, other_auth_headers)

    async with db_session.async_session_maker() as db:
        await chat_service.create_message(db, conversation_id, proposer_id, "8 giờ tối nay họp nhé")

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=confirmer_id, content="ok")

    assert await _tasks_for(confirmer_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_skips_llm_when_over_budget(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    async def _over_budget():
        return True

    monkeypatch.setattr(proactive_service.usage_service, "is_over_budget", _over_budget)

    sender_id = await _user_id(client, auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_ai_permission(client, conversation_id, auth_headers)

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=sender_id, content="đừng quên deadline gửi báo cáo thứ hai nhé"
    )

    fake_llm.ainvoke.assert_not_awaited()
    assert await _tasks_for(sender_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_never_raises_on_db_error(client, auth_headers, other_auth_headers, monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = _relevant_response()  # relevance pass must pass to even reach _load_window
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    async def _boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(proactive_service, "_load_window", _boom)

    sender_id = await _user_id(client, auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_ai_permission(client, conversation_id, auth_headers)

    # Không raise ra ngoài - lỗi phải bị nuốt bởi try/except gốc.
    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=sender_id, content="8 giờ tối nay họp nhé"
    )

    fake_llm.ainvoke.assert_awaited_once()  # the relevance pass ran; _load_window blew up before pass 2
    assert await _tasks_for(sender_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_skips_extraction_when_relevance_check_says_no(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """Khi lượt phân loại rẻ (pass 1, LLM hiểu ngữ nghĩa) trả relevant=false, không được chạy tiếp
    windowed extraction (pass 2) - tiết kiệm chi phí đúng ràng buộc đề bài, thay cho regex
    pre-filter cũ (xem WORKLOG 2026-08-12: regex bỏ sót "tôi cũng ok nhé")."""
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = _relevant_response(False)
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    sender_id = await _user_id(client, auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    await _grant_ai_permission(client, conversation_id, auth_headers)

    await proactive_service.maybe_suggest_task(conversation_id=conversation_id, sender_id=sender_id, content="thanks!")

    fake_llm.ainvoke.assert_awaited_once()  # only the relevance pass, never the windowed extraction
    assert await _tasks_for(sender_id) == []


@pytest.mark.asyncio
async def test_maybe_suggest_task_skips_when_ai_permission_not_granted(
    client, auth_headers, other_auth_headers, monkeypatch
):
    fake_llm = AsyncMock()
    monkeypatch.setattr(proactive_service, "get_llm", lambda: fake_llm)

    sender_id = await _user_id(client, auth_headers)
    conversation_id = await _create_conversation(client, auth_headers, other_auth_headers)
    # Permission was never granted for this conversation - default deny.

    await proactive_service.maybe_suggest_task(
        conversation_id=conversation_id, sender_id=sender_id, content="đừng quên deadline gửi báo cáo thứ hai nhé"
    )

    fake_llm.ainvoke.assert_not_awaited()
    assert await _tasks_for(sender_id) == []
