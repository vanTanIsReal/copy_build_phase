"""Quality Assurance agent's specialist tools.

Real vertical slice for the ``quality_assurance`` agent profile - the QA counterpart of
``src.agents.tools.delivery_tool``. Same shape: plain async callables returning ``ToolResult``,
every function re-checks the caller's ``AgentContext`` live via
``resource_guard.enforce_agent_workspace_access`` before touching data (G2), reads go through
``src.services.quality_workspace_service`` (real Postgres, scoped to ``agent_workspace_id``).

``release_readiness`` is never decided by the LLM - it comes straight from
``quality_workspace_service.compute_release_readiness``, a pure function with one hard rule any
open critical bug makes a release NOT_READY (MULTI_AGENT_IMPLEMENTATION_PLAN.md #6.2, and this
project's hard constraint #1: "Policy bằng code, không phải prompt").
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
    ReleaseReadiness,
    SourceReference,
    ToolResult,
    ToolResultStatus,
    WorkspaceBrief,
    action_payload_hash,
)
from src.agents.policies.resource_guard import enforce_agent_workspace_access
from src.agents.schemas.quality import QualityBriefPayload
from src.agents.tools.registry import assert_tool_allowed
from src.services import quality_workspace_service, workspace_brief_service

_TOOL_NAMES: tuple[str, ...] = (
    "get_quality_work_items",
    "search_quality_messages",
    "get_release_test_status",
    "get_quality_people",
    "build_quality_brief",
    "propose_quality_reminder",
    "propose_quality_meeting",
)

for _name in _TOOL_NAMES:
    assert_tool_allowed(AgentProfile.QUALITY_ASSURANCE, _name)


def _workspace_id(context: AgentContext) -> str:
    workspace_id = context.request.target_agent_workspace_id
    if not workspace_id:
        raise ValueError("Quality tools require an AgentContext with a target_agent_workspace_id")
    return workspace_id


def _source(resource_id: str, resource_type: str, agent_workspace_id: str) -> SourceReference:
    return SourceReference(
        resource_id=resource_id,
        resource_type=resource_type,
        agent_workspace_id=agent_workspace_id,
        classification="internal",
        captured_at=datetime.now(UTC),
    )


def _work_item_dict(item) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "work_item_type": item.work_item_type,
        "severity": item.severity,
        "quality_status": item.quality_status,
        "owner_id": item.owner_id,
        "due_at": item.due_at.isoformat() if item.due_at else None,
    }


async def get_quality_work_items(
    db: AsyncSession, context: AgentContext, *, work_item_type: str | None = None
) -> ToolResult:
    """Read-only: list bug/test_case/release_check work items in this QA workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    items = await quality_workspace_service.list_work_items(db, workspace_id, work_item_type=work_item_type)
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"work_items": [_work_item_dict(item) for item in items]},
        sources=(_source("quality-work-items-snapshot", "work_item_list", workspace_id),),
    )


async def search_quality_messages(
    db: AsyncSession, context: AgentContext, *, query: str = "", limit: int = 10
) -> ToolResult:
    """Read-only: keyword search over messages in conversations linked to this QA workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    rows = await quality_workspace_service.search_messages(db, workspace_id, query, limit=limit)
    messages = [
        {"id": message.id, "author_id": message.sender_id, "content": message.content, "sent_at": message.created_at.isoformat()}
        for message, _sender in rows
    ]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"query": query, "messages": messages},
        sources=(_source("quality-messages-snapshot", "message_list", workspace_id),),
    )


async def get_release_test_status(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Read-only: release_readiness computed by code (not the LLM) from real work-item facts."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    items = await quality_workspace_service.list_work_items(db, workspace_id)
    readiness, blocking_items = quality_workspace_service.compute_release_readiness(items)
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={
            "release_readiness": readiness,
            "blocking_items": [_work_item_dict(item) for item in blocking_items],
            "total_work_items": len(items),
        },
        sources=(_source("quality-release-status-snapshot", "release_status", workspace_id),),
    )


async def get_quality_people(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Read-only: list active members of the Quality Assurance agent workspace."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    members = await quality_workspace_service.list_members(db, workspace_id)
    people = [{"id": user.id, "name": user.display_name, "role": role} for user, role in members]
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"people": people},
        sources=(_source("quality-people-snapshot", "person_list", workspace_id),),
    )


async def build_quality_brief(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Brief producer: assemble a QualityBriefPayload from real work items and wrap it in a
    validated WorkspaceBrief with release_readiness set (required for BriefType.QUALITY)."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    items = await quality_workspace_service.list_work_items(db, workspace_id)
    readiness, blocking_items = quality_workspace_service.compute_release_readiness(items)
    critical_defects = [
        item for item in items if item.work_item_type == "bug" and item.severity == "critical"
    ]
    blocked_tests = [item for item in items if item.work_item_type == "test_case" and item.quality_status == "blocked"]
    test_progress = {
        "total": len([i for i in items if i.work_item_type == "test_case"]),
        "passed": len([i for i in items if i.work_item_type == "test_case" and i.quality_status == "passed"]),
        "failed": len([i for i in items if i.work_item_type == "test_case" and i.quality_status == "failed"]),
    }

    headline = {
        "NOT_READY": f"Release NOT_READY: {len(blocking_items)} critical bug còn mở.",
        "AT_RISK": f"Release AT_RISK: {len(blocking_items)} work item failed/blocked.",
        "READY": "Release READY: không có critical bug hoặc test failed/blocked.",
    }[readiness]

    payload = QualityBriefPayload(
        headline=headline,
        release_readiness=ReleaseReadiness(readiness),
        test_progress=test_progress,
        critical_defects=[_work_item_dict(item) for item in critical_defects],
        blocked_tests=[_work_item_dict(item) for item in blocked_tests],
    )

    contributing_ids = [item.id for item in critical_defects] + [item.id for item in blocked_tests]
    sources = tuple(_source(item_id, "quality_fact", workspace_id) for item_id in contributing_ids)

    now = datetime.now(UTC)
    brief = WorkspaceBrief(
        brief_id=f"quality-brief-{uuid4()}",
        trace_id=context.trace_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_workspace_id=workspace_id,
        brief_type=BriefType.QUALITY,
        producer_profile=AgentProfile.QUALITY_ASSURANCE,
        period_start=now - timedelta(days=7),
        period_end=now,
        generated_at=now,
        expires_at=now + timedelta(hours=24),
        headline=payload.headline,
        facts=tuple(payload.critical_defects) + tuple(payload.blocked_tests),
        sources=sources,
        release_readiness=ReleaseReadiness(readiness),
    )
    await workspace_brief_service.save_brief(db, brief)

    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={
            "quality_brief": payload.model_dump(mode="json"),
            "workspace_brief": brief.model_dump(mode="json"),
        },
        sources=sources,
    )


async def propose_quality_reminder(
    db: AsyncSession, context: AgentContext, *, title: str, due_at: datetime, message: str = ""
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a QA reminder. Never schedules anything."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    now = datetime.now(UTC)
    draft_payload = {"title": title, "due_at": due_at.isoformat(), "message": message}
    proposal = ActionProposal(
        proposal_id=f"quality-reminder-{uuid4()}",
        trace_id=context.trace_id,
        actor_user_id=context.actor.user_id,
        action="preview_quality_reminder",
        payload=draft_payload,
        payload_hash=action_payload_hash(draft_payload),
        idempotency_key=f"quality-reminder-{uuid4()}",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"proposal": proposal.model_dump(mode="json"), "requires_confirmation": True},
        sources=(_source("quality-reminder-preview", "action_proposal", workspace_id),),
    )


async def propose_quality_meeting(
    db: AsyncSession,
    context: AgentContext,
    *,
    title: str,
    starts_at: datetime,
    attendee_ids: tuple[str, ...] = (),
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a QA meeting. Never creates a calendar event."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    now = datetime.now(UTC)
    draft_payload = {
        "title": title,
        "starts_at": starts_at.isoformat(),
        "attendee_ids": list(attendee_ids),
    }
    proposal = ActionProposal(
        proposal_id=f"quality-meeting-{uuid4()}",
        trace_id=context.trace_id,
        actor_user_id=context.actor.user_id,
        action="preview_quality_meeting",
        payload=draft_payload,
        payload_hash=action_payload_hash(draft_payload),
        idempotency_key=f"quality-meeting-{uuid4()}",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"proposal": proposal.model_dump(mode="json"), "requires_confirmation": True},
        sources=(_source("quality-meeting-preview", "action_proposal", workspace_id),),
    )
