"""Quality Assurance agent's brief/proposal tools.

Real vertical slice for the ``quality_assurance`` agent profile registered in
``src.agents.tools.registry``, completing "Ngày 3 - Runtime và Quality WorkspaceBrief" from
``docs/ROLE_C_QUALITY_ASSURANCE_7_DAY_PLAN.md`` (stopped at "Ngày 2 - scoped reads" before this).
Mirrors ``src.agents.tools.delivery_tool``'s shape exactly: plain async callables (NOT LangChain
``@tool``) returning the shared ``ToolResult`` contract, re-checking ``AgentContext`` live via
``resource_guard.enforce_agent_workspace_access`` before touching any data (G2).

``get_quality_snapshot`` (``quality_snapshot.py``) and ``search_quality_evidence``
(``quality_evidence.py``) already existed and are unchanged by this module - they cover
conversation-evidence-sourced reads. This module adds the two tools that were still missing:

- ``build_quality_brief``: reads Task rows tagged as QA work items (same "reuse Task instead of a
  parallel work-item table" decision ``delivery_tool.py`` already made - see
  ``quality_workspace_service.list_quality_work_items``), runs the frozen, already-tested
  ``evaluate_release_readiness`` rule engine (code, never a model, decides READY/AT_RISK/
  NOT_READY - ``src/agents/profiles/quality_assurance.py``), and wraps the result in a validated
  ``WorkspaceBrief`` the same way ``build_delivery_brief``/``build_executive_brief`` do. Zero LLM
  calls, same as the rest of the specialist-brief pipeline.
- ``propose_quality_reminder``/``propose_quality_meeting``: draft-only ``ActionProposal`` previews
  for the shared HITL executor, never a real side effect until a human confirms via
  ``/chat/resume``. ``docs/ROLE_C_QUALITY_ASSURANCE_7_DAY_PLAN.md`` §5 also describes
  ``bug_assignment``/``bug_status_update`` action types under one ``propose_quality_action`` tool -
  deliberately NOT implemented here: neither has any real side-effect service to call yet (unlike
  reminder/meeting, which reuse the same ``reminder_service``/``calendar_service`` Delivery already
  uses), and changing a bug's status has direct consequences for
  ``evaluate_release_readiness`` that need their own design pass, not a same-day bolt-on.
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
from src.agents.profiles.quality_assurance import evaluate_release_readiness
from src.agents.schemas.quality import (
    QualitySeverity,
    QualityStatus,
    QualityWorkItem,
    QualityWorkItemType,
)
from src.agents.tools.registry import assert_tool_allowed
from src.services import quality_workspace_service, workspace_brief_service

_TOOL_NAMES: tuple[str, ...] = (
    "build_quality_brief",
    "propose_quality_reminder",
    "propose_quality_meeting",
)

# Fail fast at import time if a name here ever drifts from the registry's QUALITY_ASSURANCE
# allowlist (assert_tool_allowed raises PermissionError) - same convention as delivery_tool.py.
# get_quality_snapshot/search_quality_evidence are asserted-allowed by the registry too, but live
# in their own modules (quality_snapshot.py/quality_evidence.py) and are unchanged here.
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
        classification="quality",
        captured_at=datetime.now(UTC),
    )


def _task_to_work_item(task) -> QualityWorkItem | None:
    """None for a Task that's tagged as a QA work item (work_item_type set - already filtered by
    list_quality_work_items) but missing/invalid severity or quality_status - malformed data is
    reported as a data gap by the caller, never silently coerced into a fake default."""
    try:
        return QualityWorkItem(
            work_item_id=task.id,
            title=task.title,
            work_item_type=QualityWorkItemType(task.work_item_type),
            severity=QualitySeverity(task.severity),
            quality_status=QualityStatus(task.quality_status),
            source_id=task.id,
            release_id=task.release_target,
        )
    except ValueError:
        return None


async def build_quality_brief(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Brief producer: run the deterministic readiness rules over real QA work items and wrap the
    result in a validated Quality WorkspaceBrief (release_readiness is REQUIRED for BriefType.
    QUALITY - WorkspaceBrief's own validator raises otherwise).

    required_release_check_ids (evaluate_release_readiness's own required input, see
    src/agents/profiles/quality_assurance.py) = every release_check item currently in scope - there
    is no separate "is this check required" flag in the data model yet, so an MVP-honest choice is
    "every declared release check for this workspace is required"; a future slice could narrow this
    to a specific release_id.
    """
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)

    tasks = await quality_workspace_service.list_quality_work_items(db, workspace_id)
    work_items: list[QualityWorkItem] = []
    malformed = 0
    for task in tasks:
        item = _task_to_work_item(task)
        if item is None:
            malformed += 1
        else:
            work_items.append(item)

    required_release_check_ids = tuple(
        item.work_item_id for item in work_items if item.work_item_type == QualityWorkItemType.RELEASE_CHECK
    )
    assessment = evaluate_release_readiness(work_items, required_release_check_ids=required_release_check_ids)

    data_gaps = list(assessment.data_gaps)
    if malformed:
        data_gaps.append(f"{malformed} QA work item(s) had missing/invalid severity or status and were excluded.")

    contributing_ids = list(dict.fromkeys(item.work_item_id for item in work_items))
    sources = tuple(_source(work_item_id, "quality_fact", workspace_id) for work_item_id in contributing_ids)

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
        headline=f"Release {assessment.release_readiness.value}: "
        f"{len(assessment.critical_defects)} critical defect, "
        f"{len(assessment.blocked_tests)} failed/blocked test.",
        facts=tuple(item.model_dump(mode="json") for item in work_items),
        risks=tuple(finding.model_dump(mode="json") for finding in assessment.quality_risks),
        data_gaps=tuple(data_gaps),
        sources=sources,
        release_readiness=assessment.release_readiness,
    )
    await workspace_brief_service.save_brief(db, brief)

    return ToolResult(
        status=ToolResultStatus.PARTIAL if data_gaps else ToolResultStatus.SUCCESS,
        payload={
            "quality_brief": assessment.model_dump(mode="json"),
            "workspace_brief": brief.model_dump(mode="json"),
        },
        data_gaps=tuple(data_gaps),
        sources=sources,
    )


async def propose_quality_reminder(
    db: AsyncSession,
    context: AgentContext,
    *,
    title: str,
    due_at: datetime,
    message: str = "",
) -> ToolResult:
    """Preview-only: draft an ActionProposal for a QA reminder. Never schedules anything - a human
    must confirm via the HITL executor before this has any real effect."""
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
    """Preview-only: draft an ActionProposal for a QA meeting. Never creates a calendar event - a
    human must confirm via the HITL executor before this has any real effect."""
    workspace_id = _workspace_id(context)
    await enforce_agent_workspace_access(db, context=context, agent_workspace_id=workspace_id)
    try:
        await validate_attendee_ids(
            db, organization_workspace_id=context.actor.organization_workspace_id, attendee_ids=attendee_ids
        )
    except InvalidAttendeeError as exc:
        return ToolResult(status=ToolResultStatus.ERROR, error_code="INVALID_ATTENDEE", error_message=str(exc))

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
