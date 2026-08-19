"""Product Delivery agent's specialist tools.

Mock vertical slice for the ``product_delivery`` agent profile registered in
``src.agents.tools.registry``. Every function here is a plain async callable (NOT a LangChain
``@tool``) returning the shared ``ToolResult`` contract from ``src.agents.contracts`` — this is
the tool boundary shape the multi-agent workspace foundation expects specialist agents to speak,
independent of the LangGraph ``@tool`` wiring the PERSONAL profile still uses in ``graph.py``.

Data below is mocked (no DB/service calls yet): the foundation's Resource Guard and Scope
Resolver aren't wired to a real Delivery data source. Real reads/writes land once the Delivery
brief producer graduates past fixtures (see docs/MULTI_AGENT_PROGRESS.md, "Thứ tự công việc tiếp
theo"). Every returned ``SourceReference.agent_workspace_id`` matches the caller-supplied
``agent_workspace_id`` so downstream WorkspaceBrief.sources ownership checks hold.

``propose_delivery_reminder``/``propose_delivery_meeting`` never create anything — they only
preview an ``ActionProposal`` for a human to confirm later, per the project's human-in-the-loop
rule for any tool with a side effect (see CLAUDE.md). Actually scheduling the reminder/meeting is
the HITL executor's job (not yet built), not this module's.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.agents.contracts import (
    ActionProposal,
    AgentProfile,
    BriefType,
    SourceReference,
    ToolResult,
    ToolResultStatus,
    WorkspaceBrief,
    action_payload_hash,
)
from src.agents.schemas.delivery import DeliveryBriefPayload
from src.agents.tools.registry import assert_tool_allowed

DEFAULT_ORGANIZATION_WORKSPACE_ID = "org_orbit_demo"
DEFAULT_AGENT_WORKSPACE_ID = "agent_ws_product_delivery"

_MOCK_TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "delivery-task-001",
        "title": "API đăng nhập",
        "status": "blocked",
        "priority": "high",
        "owner_id": "delivery-user-1",
        "due_at": "2026-08-20T00:00:00+00:00",
        "blocked_reason": "Thiếu refresh-token contract từ nhóm nền tảng",
    },
    {
        "id": "delivery-task-002",
        "title": "Trang release",
        "status": "due_soon",
        "priority": "medium",
        "owner_id": "delivery-user-2",
        "due_at": "2026-08-19T00:00:00+00:00",
        "blocked_reason": None,
    },
    {
        "id": "delivery-task-003",
        "title": "Audit dashboard",
        "status": "in_progress",
        "priority": "medium",
        "owner_id": "delivery-user-3",
        "due_at": "2026-08-25T00:00:00+00:00",
        "blocked_reason": None,
    },
)

_MOCK_MILESTONES: tuple[dict[str, Any], ...] = (
    {
        "id": "delivery-milestone-001",
        "name": "Release R1 — Đăng nhập & Onboarding",
        "due_date": "2026-08-22",
        "status": "at_risk",
    },
    {
        "id": "delivery-milestone-002",
        "name": "Release R1 — Calendar sync",
        "due_date": "2026-08-29",
        "status": "on_track",
    },
)

_MOCK_PEOPLE: tuple[dict[str, Any], ...] = (
    {"id": "delivery-lead", "name": "Delivery Lead", "role": "lead"},
    {"id": "delivery-user-1", "name": "Delivery Member 1", "role": "member"},
    {"id": "delivery-user-2", "name": "Delivery Member 2", "role": "member"},
    {"id": "delivery-user-3", "name": "Delivery Member 3", "role": "member"},
)

_MOCK_MESSAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "delivery-message-001",
        "author_id": "delivery-user-1",
        "content": "API đăng nhập: thiếu refresh-token contract từ nhóm nền tảng",
        "sent_at": "2026-08-17T09:15:00+00:00",
    },
    {
        "id": "delivery-message-002",
        "author_id": "delivery-lead",
        "content": "Trang release đang chờ review responsive",
        "sent_at": "2026-08-17T14:30:00+00:00",
    },
    {
        "id": "delivery-message-003",
        "author_id": "delivery-user-3",
        "content": "Audit dashboard đang hoàn thiện filter theo trace",
        "sent_at": "2026-08-18T08:00:00+00:00",
    },
)

_DEPENDENCY: dict[str, Any] = {
    "id": "delivery-dependency-001",
    "from_agent_workspace_id": DEFAULT_AGENT_WORKSPACE_ID,
    "to_agent_workspace_id": "agent_ws_quality_assurance",
    "description": "Release R1 chờ Quality regression gate trước khi freeze.",
}

_DECISION: dict[str, Any] = {
    "id": "delivery-decision-001",
    "question": "Có trì hoãn Release R1 sang tuần sau để chờ QA gate không?",
    "owner_id": "delivery-lead",
    "due_date": "2026-08-21",
}

_TOOL_NAMES: tuple[str, ...] = (
    "get_delivery_tasks",
    "search_delivery_messages",
    "get_delivery_milestones",
    "get_delivery_people",
    "build_delivery_brief",
    "propose_delivery_reminder",
    "propose_delivery_meeting",
)

# Fail fast at import time if a name here ever drifts from the registry's PRODUCT_DELIVERY
# allowlist (assert_tool_allowed raises PermissionError) - the registry, not this module, is the
# source of truth for what a Delivery agent may call.
for _name in _TOOL_NAMES:
    assert_tool_allowed(AgentProfile.PRODUCT_DELIVERY, _name)


def _source(resource_id: str, resource_type: str, agent_workspace_id: str) -> SourceReference:
    return SourceReference(
        resource_id=resource_id,
        resource_type=resource_type,
        agent_workspace_id=agent_workspace_id,
        classification="internal",
        captured_at=datetime.now(UTC),
    )


async def get_delivery_tasks(
    agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID,
    *,
    include_completed: bool = False,
) -> ToolResult:
    """Read-only: list tasks tracked in the Delivery agent workspace."""
    tasks = list(_MOCK_TASKS)
    if not include_completed:
        tasks = [task for task in tasks if task["status"] != "completed"]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"tasks": tasks},
        sources=(_source("delivery-tasks-snapshot", "task_list", agent_workspace_id),),
    )


async def search_delivery_messages(
    query: str = "",
    agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID,
    limit: int = 10,
) -> ToolResult:
    """Read-only: keyword search over Delivery workspace conversation messages."""
    needle = query.strip().lower()
    matches = [message for message in _MOCK_MESSAGES if not needle or needle in message["content"].lower()]
    matches = matches[: max(1, limit)]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"query": query, "messages": matches},
        sources=(_source("delivery-messages-snapshot", "message_list", agent_workspace_id),),
    )


async def get_delivery_milestones(agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID) -> ToolResult:
    """Read-only: list Delivery workspace milestones and their status."""
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"milestones": list(_MOCK_MILESTONES)},
        sources=(_source("delivery-milestones-snapshot", "milestone_list", agent_workspace_id),),
    )


async def get_delivery_people(agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID) -> ToolResult:
    """Read-only: list people who are members of the Delivery agent workspace."""
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"people": list(_MOCK_PEOPLE)},
        sources=(_source("delivery-people-snapshot", "person_list", agent_workspace_id),),
    )


async def build_delivery_brief(
    agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID,
    organization_workspace_id: str = DEFAULT_ORGANIZATION_WORKSPACE_ID,
    trace_id: str = "trace-delivery-mock",
) -> ToolResult:
    """Brief producer: assemble a DeliveryBriefPayload and wrap it in a validated WorkspaceBrief.

    ``release_readiness`` is deliberately left unset - WorkspaceBrief.validate_brief_envelope
    raises if a DELIVERY brief carries one (that field belongs only to a Quality brief).
    """
    blocked_items = [task for task in _MOCK_TASKS if task["status"] == "blocked"]
    payload = DeliveryBriefPayload(
        headline="Delivery tuần này: 1 milestone at-risk, 1 task blocked chờ dependency ngoài team.",
        milestones=list(_MOCK_MILESTONES),
        blocked_items=blocked_items,
        dependencies=[_DEPENDENCY],
        decisions_needed=[_DECISION],
    )

    contributing_ids = (
        [milestone["id"] for milestone in _MOCK_MILESTONES]
        + [task["id"] for task in blocked_items]
        + [_DEPENDENCY["id"], _DECISION["id"]]
    )
    sources = tuple(
        _source(resource_id, "delivery_fact", agent_workspace_id) for resource_id in contributing_ids
    )

    now = datetime.now(UTC)
    brief = WorkspaceBrief(
        brief_id=f"delivery-brief-{uuid4()}",
        trace_id=trace_id,
        organization_workspace_id=organization_workspace_id,
        agent_workspace_id=agent_workspace_id,
        brief_type=BriefType.DELIVERY,
        producer_profile=AgentProfile.PRODUCT_DELIVERY,
        period_start=now - timedelta(days=7),
        period_end=now,
        generated_at=now,
        expires_at=now + timedelta(hours=24),
        headline=payload.headline,
        facts=tuple(payload.milestones) + tuple(payload.blocked_items),
        dependencies=tuple(payload.dependencies),
        decisions_needed=tuple(payload.decisions_needed),
        sources=sources,
        # release_readiness intentionally omitted - stays None, as required for BriefType.DELIVERY.
    )

    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={
            "delivery_brief": payload.model_dump(),
            "workspace_brief": brief.model_dump(mode="json"),
        },
        sources=sources,
    )


async def propose_delivery_reminder(
    title: str,
    due_at: datetime,
    agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID,
    actor_user_id: str = "delivery-lead",
    message: str = "",
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a Delivery reminder. Never schedules anything -
    a human must confirm via the HITL executor before this has any real effect."""
    now = datetime.now(UTC)
    draft_payload = {"title": title, "due_at": due_at.isoformat(), "message": message}
    proposal = ActionProposal(
        proposal_id=f"delivery-reminder-{uuid4()}",
        trace_id=f"trace-{uuid4()}",
        actor_user_id=actor_user_id,
        action="preview_delivery_reminder",
        payload=draft_payload,
        payload_hash=action_payload_hash(draft_payload),
        idempotency_key=f"delivery-reminder-{uuid4()}",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"proposal": proposal.model_dump(mode="json"), "requires_confirmation": True},
        sources=(_source("delivery-reminder-preview", "action_proposal", agent_workspace_id),),
    )


async def propose_delivery_meeting(
    title: str,
    starts_at: datetime,
    agent_workspace_id: str = DEFAULT_AGENT_WORKSPACE_ID,
    actor_user_id: str = "delivery-lead",
    attendee_ids: tuple[str, ...] = (),
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a Delivery meeting. Never creates a calendar
    event - a human must confirm via the HITL executor before this has any real effect."""
    now = datetime.now(UTC)
    draft_payload = {
        "title": title,
        "starts_at": starts_at.isoformat(),
        "attendee_ids": list(attendee_ids),
    }
    proposal = ActionProposal(
        proposal_id=f"delivery-meeting-{uuid4()}",
        trace_id=f"trace-{uuid4()}",
        actor_user_id=actor_user_id,
        action="preview_delivery_meeting",
        payload=draft_payload,
        payload_hash=action_payload_hash(draft_payload),
        idempotency_key=f"delivery-meeting-{uuid4()}",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"proposal": proposal.model_dump(mode="json"), "requires_confirmation": True},
        sources=(_source("delivery-meeting-preview", "action_proposal", agent_workspace_id),),
    )
