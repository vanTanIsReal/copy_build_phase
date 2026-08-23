"""Product Delivery agent's specialist tools.

Real vertical slice for the ``product_delivery`` agent profile registered in
``src.agents.tools.registry``. Every function here is a plain async callable (NOT a LangChain
``@tool``) returning the shared ``ToolResult`` contract from ``src.agents.contracts`` - the tool
boundary shape the multi-agent workspace foundation expects specialist agents to speak,
independent of the LangGraph ``@tool`` wiring the PERSONAL profile still uses in ``graph.py``.

Every function takes the caller's ``AgentContext`` and re-checks it live via
``resource_guard.enforce_agent_workspace_access`` before touching any data (G2) - the context's own
``authorization.decision`` is a snapshot from the start of the turn and is NOT trusted on its own.
Reads go through ``src.services.delivery_workspace_service`` (real Postgres, scoped to
``agent_workspace_id``); no fixture/mock data. Milestones and cross-workspace dependencies are not
yet modeled as their own DB records - callers get an honest ``data_gaps`` entry instead of
fabricated content (G4: "Không có source thì ghi inference/data gap, không biến suy đoán thành
fact").

``propose_delivery_reminder``/``propose_delivery_meeting`` never create anything - they only draft
an ``ActionProposal`` for the shared HITL executor (``src.agents.hitl_executor``) to actually run
once a human confirms, per CLAUDE.md's human-in-the-loop rule for any tool with a side effect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import (
    ActionProposal,
    AgentContext,
    AgentProfile,
    BriefType,
    SourceReference,
    ToolResult,
    ToolResultStatus,
    WorkspaceBrief,
    action_payload_hash,
)
from src.agents.policies.resource_guard import enforce_agent_workspace_access
from src.agents.policies.scope_resolver import InvalidAttendeeError, validate_attendee_ids
from src.agents.schemas.delivery import DeliveryBriefPayload
from src.agents.tools.registry import assert_tool_allowed
from src.services import delivery_workspace_service, workspace_brief_service

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


def _workspace_id(context: AgentContext) -> str:
    workspace_id = context.request.target_agent_workspace_id
    if not workspace_id:
        raise ValueError("Delivery tools require an AgentContext with a target_agent_workspace_id")
    return workspace_id


def _source(resource_id: str, resource_type: str, agent_workspace_id: str) -> SourceReference:
    return SourceReference(
        resource_id=resource_id,
        resource_type=resource_type,
        agent_workspace_id=agent_workspace_id,
        classification="internal",
        captured_at=datetime.now(UTC),
    )


def _task_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "owner_id": task.owner_id,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "needs_clarification": task.needs_clarification,
        "release_target": task.release_target,
    }


async def get_delivery_tasks(
    db: AsyncSession, context: AgentContext, *, include_completed: bool = False
) -> ToolResult:
    """Read-only: list tasks tracked in the caller's Delivery agent workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    tasks = await delivery_workspace_service.list_tasks(db, workspace_id, include_completed=include_completed)
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"tasks": [_task_dict(task) for task in tasks]},
        sources=(_source("delivery-tasks-snapshot", "task_list", workspace_id),),
    )


async def search_delivery_messages(
    db: AsyncSession, context: AgentContext, *, query: str = "", limit: int = 10
) -> ToolResult:
    """Read-only: keyword search over messages in conversations linked to this Delivery workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    rows = await delivery_workspace_service.search_messages(db, workspace_id, query, limit=limit)
    messages = [
        {"id": message.id, "author_id": message.sender_id, "content": message.content, "sent_at": message.created_at.isoformat()}
        for message, _sender in rows
    ]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"query": query, "messages": messages},
        sources=(_source("delivery-messages-snapshot", "message_list", workspace_id),),
    )


async def get_delivery_milestones(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Read-only: milestones are not yet their own DB record (see module docstring) - reports an
    honest empty result with a data gap instead of fabricating milestone content."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    return ToolResult(
        status=ToolResultStatus.PARTIAL,
        payload={"milestones": []},
        data_gaps=("Milestone tracking is not yet modeled beyond Task - only task-level status is available.",),
        sources=(_source("delivery-milestones-snapshot", "milestone_list", workspace_id),),
    )


async def get_delivery_people(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Read-only: list active members of the Delivery agent workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    members = await delivery_workspace_service.list_members(db, workspace_id)
    people = [{"id": user.id, "name": user.display_name, "role": role} for user, role in members]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"people": people},
        sources=(_source("delivery-people-snapshot", "person_list", workspace_id),),
    )


async def build_delivery_brief(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Brief producer: assemble a DeliveryBriefPayload from real tasks and wrap it in a validated
    WorkspaceBrief. ``release_readiness`` is deliberately left unset - WorkspaceBrief's own
    validator raises if a DELIVERY brief carries one (that field belongs only to a Quality brief).

    ``dependencies`` carries every task that has ``release_target`` set (MULTI_AGENT_IMPLEMENTATION_
    PLAN.md Ngày 4 "cross-workspace scenario") - this is the self-describing tag a Quality brief with
    a matching release_target links back to. Executive cross-references the two briefs'
    release_targets itself (see executive_tool.get_cross_workspace_dependencies); this tool does not
    reach into another workspace's data to do that matching, staying within its own scope (G2).
    Full milestone tracking (due dates, status beyond a task's own) is still not modeled - see
    get_delivery_milestones's own data gap.
    """
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    tasks = await delivery_workspace_service.list_tasks(db, workspace_id)
    blocked = [task for task in tasks if task.status == "blocked"]
    needs_clarification = [task for task in tasks if task.needs_clarification]
    release_linked = [task for task in tasks if task.release_target]
    data_gaps: list[str] = ["Milestone tracking is not yet modeled beyond Task."]

    if blocked:
        headline = f"Delivery: {len(blocked)} task đang blocked, cần xử lý trước khi tiếp tục."
    elif needs_clarification:
        headline = f"Delivery: {len(needs_clarification)} task còn thiếu owner/deadline rõ ràng."
    else:
        headline = f"Delivery: {len(tasks)} task đang mở, không có task nào bị blocked."

    payload = DeliveryBriefPayload(
        headline=headline,
        milestones=[],
        blocked_items=[_task_dict(task) for task in blocked],
        dependencies=[_task_dict(task) for task in release_linked],
        decisions_needed=[_task_dict(task) for task in needs_clarification],
    )

    # Every open task is now a fact (see the WorkspaceBrief construction below) - sources cover
    # the same set, so every fact has a matching provenance entry (G4).
    contributing_ids = list(dict.fromkeys(task.id for task in tasks))
    sources = tuple(_source(task_id, "delivery_fact", workspace_id) for task_id in contributing_ids)

    now = datetime.now(UTC)
    brief = WorkspaceBrief(
        brief_id=f"delivery-brief-{uuid4()}",
        trace_id=context.trace_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_workspace_id=workspace_id,
        brief_type=BriefType.DELIVERY,
        producer_profile=AgentProfile.PRODUCT_DELIVERY,
        period_start=now - timedelta(days=7),
        period_end=now,
        generated_at=now,
        expires_at=now + timedelta(hours=24),
        headline=payload.headline,
        # Every currently-open task, not only blocked/needs-clarification ones - a due-soon or
        # in-progress task with no problem flag is still a real fact about this workspace's state
        # (MULTI_AGENT_IMPLEMENTATION_PLAN.md #6.1: "Tổng hợp milestone, overdue, due soon,
        # blocked..."). Deduplicated so a task that's both blocked and needs_clarification isn't
        # listed twice.
        facts=tuple({task["id"]: task for task in ([_task_dict(t) for t in tasks])}.values()),
        dependencies=tuple(payload.dependencies),
        decisions_needed=tuple(payload.decisions_needed),
        data_gaps=tuple(data_gaps),
        sources=sources,
        # release_readiness intentionally omitted - stays None, as required for BriefType.DELIVERY.
    )
    await workspace_brief_service.save_brief(db, brief)

    return ToolResult(
        status=ToolResultStatus.PARTIAL if data_gaps else ToolResultStatus.SUCCESS,
        payload={
            "delivery_brief": payload.model_dump(),
            "workspace_brief": brief.model_dump(mode="json"),
        },
        data_gaps=tuple(data_gaps),
        sources=sources,
    )


async def propose_delivery_reminder(
    db: AsyncSession,
    context: AgentContext,
    *,
    title: str,
    due_at: datetime,
    message: str = "",
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a Delivery reminder. Never schedules anything -
    a human must confirm via the HITL executor before this has any real effect."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    now = datetime.now(UTC)
    draft_payload = {"title": title, "due_at": due_at.isoformat(), "message": message}
    proposal = ActionProposal(
        proposal_id=f"delivery-reminder-{uuid4()}",
        trace_id=context.trace_id,
        actor_user_id=context.actor.user_id,
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
        sources=(_source("delivery-reminder-preview", "action_proposal", workspace_id),),
    )


async def propose_delivery_meeting(
    db: AsyncSession,
    context: AgentContext,
    *,
    title: str,
    starts_at: datetime,
    attendee_ids: tuple[str, ...] = (),
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a Delivery meeting. Never creates a calendar
    event - a human must confirm via the HITL executor before this has any real effect."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)
    try:
        await validate_attendee_ids(
            db, organization_workspace_id=context.actor.organization_workspace_id, attendee_ids=attendee_ids
        )
    except InvalidAttendeeError as exc:
        return ToolResult(
            status=ToolResultStatus.ERROR, error_code="INVALID_ATTENDEE", error_message=str(exc)
        )

    now = datetime.now(UTC)
    draft_payload = {
        "title": title,
        "starts_at": starts_at.isoformat(),
        "attendee_ids": list(attendee_ids),
    }
    proposal = ActionProposal(
        proposal_id=f"delivery-meeting-{uuid4()}",
        trace_id=context.trace_id,
        actor_user_id=context.actor.user_id,
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
        sources=(_source("delivery-meeting-preview", "action_proposal", workspace_id),),
    )
