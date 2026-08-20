"""Executive agent's specialist tools.

Same shape as delivery_tool.py/quality_tool.py: plain async callables returning ``ToolResult``,
every function re-checks the caller's ``AgentContext`` live (G2) before touching data. The
Executive profile's scope is always AGGREGATE (no ``target_agent_workspace_id`` - see
``router.route_agent_request``), so its guard re-runs ``resolve_agent_scope`` directly instead of
going through ``resource_guard.enforce_agent_workspace_access`` (which is Delivery/Quality-only:
it requires a single ``target_agent_workspace_id``).

Executive NEVER reads raw chat/task rows - only already-published, schema-validated
``WorkspaceBrief`` records (``src.services.workspace_brief_service``) it's entitled to see via
``AuthorizationContext.allowed_agent_workspace_ids`` (populated by scope_resolver from the
caller's ``executive_viewer`` memberships). A brief that's missing or stale becomes a `data_gaps`
entry, never fabricated content (G4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import (
    ActionProposal,
    AgentContext,
    AgentProfile,
    ExecutiveBrief,
    PolicyDecision,
    SourceReference,
    ToolResult,
    ToolResultStatus,
    action_payload_hash,
)
from src.agents.policies.resource_guard import AgentResourceDeniedError
from src.agents.policies.scope_resolver import resolve_agent_scope
from src.agents.tools.registry import assert_tool_allowed
from src.db.models import AgentWorkspace
from src.services import calendar_service, workspace_brief_service
from src.services.google_credentials import CalendarNotConnected

_TOOL_NAMES: tuple[str, ...] = (
    "get_workspace_briefs",
    "get_cross_workspace_dependencies",
    "build_executive_brief",
    "get_my_calendar",
    "propose_executive_meeting",
)

# AgentWorkspace.agent_profile ("product_delivery"/"quality_assurance") -> the BriefType value
# ("delivery"/"quality") workspace_brief_service.get_latest_brief expects. Explicit mapping instead
# of the .replace()-chain this used to be (tech debt flagged in an earlier review) - fails loudly on
# an unmapped profile instead of silently producing a lookup that matches nothing.
_BRIEF_TYPE_BY_PROFILE = {"product_delivery": "delivery", "quality_assurance": "quality"}

for _name in _TOOL_NAMES:
    assert_tool_allowed(AgentProfile.EXECUTIVE, _name)


async def _reverify(db: AsyncSession, context: AgentContext) -> tuple[str, ...]:
    """G2 for the Executive profile: re-resolve scope live and return the currently-allowed
    agent_workspace_ids (never trust the AgentContext snapshot on its own - same "stale HITL"
    principle as resource_guard, just without a single target_agent_workspace_id to compare)."""
    if context.authorization.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(context.authorization.reason)
    resolution = await resolve_agent_scope(
        db,
        user_id=context.actor.user_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_profile=AgentProfile.EXECUTIVE,
        requested_scope=context.request.requested_scope,
        target_agent_workspace_id=None,
    )
    if resolution.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(resolution.reason)
    return resolution.allowed_agent_workspace_ids


def _source(resource_id: str, resource_type: str, agent_workspace_id: str) -> SourceReference:
    return SourceReference(
        resource_id=resource_id,
        resource_type=resource_type,
        agent_workspace_id=agent_workspace_id,
        classification="internal",
        captured_at=datetime.now(UTC),
    )


async def get_workspace_briefs(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Read-only: latest Delivery and Quality briefs from every workspace the caller has
    executive_viewer entitlement in. Stale/missing briefs are reported, not silently dropped."""
    allowed_ids = await _reverify(db, context)
    workspaces = [w for w in (await db.execute(select(AgentWorkspace).where(AgentWorkspace.id.in_(allowed_ids)))).scalars().all()]

    briefs: list[dict] = []
    data_gaps: list[str] = []
    sources: list[SourceReference] = []
    for workspace in workspaces:
        brief_type = _BRIEF_TYPE_BY_PROFILE.get(workspace.agent_profile)
        if brief_type is None:
            data_gaps.append(f"Workspace '{workspace.name}' has an unrecognized agent_profile '{workspace.agent_profile}'.")
            continue
        brief = await workspace_brief_service.get_latest_brief(db, workspace.id, brief_type)
        if brief is None:
            data_gaps.append(f"No brief has been published yet for workspace '{workspace.name}'.")
            continue
        if brief.is_stale():
            data_gaps.append(f"Latest brief for workspace '{workspace.name}' expired at {brief.expires_at.isoformat()}.")
        briefs.append(brief.model_dump(mode="json"))
        sources.append(_source(brief.brief_id, "workspace_brief", workspace.id))

    return ToolResult(
        status=ToolResultStatus.PARTIAL if data_gaps else ToolResultStatus.SUCCESS,
        payload={"briefs": briefs},
        data_gaps=tuple(data_gaps),
        sources=tuple(sources),
    )


async def get_cross_workspace_dependencies(db: AsyncSession, context: AgentContext) -> ToolResult:
    """Real cross-workspace dependencies, matched purely from already-fetched brief content -
    never by querying another workspace's Task rows directly (this module's own docstring: "Executive
    NEVER reads raw chat/task rows"). Both build_delivery_brief and build_quality_brief tag their own
    release_target-linked items into WorkspaceBrief.dependencies (MULTI_AGENT_IMPLEMENTATION_PLAN.md
    Ngày 4 "cross-workspace scenario"); a Delivery item and a Quality item sharing the same
    release_target are the dependency pair returned here. Work not tagged with a release_target on
    either side is invisible to this matching - an honest data gap, not a false negative."""
    briefs_result = await get_workspace_briefs(db, context)
    briefs = briefs_result.payload["briefs"]

    delivery_items = [
        (brief, item)
        for brief in briefs
        if brief["brief_type"] == "delivery"
        for item in brief.get("dependencies", [])
        if item.get("release_target")
    ]
    quality_items = [
        (brief, item)
        for brief in briefs
        if brief["brief_type"] == "quality"
        for item in brief.get("dependencies", [])
        if item.get("release_target")
    ]

    dependencies: list[dict] = []
    for delivery_brief, delivery_item in delivery_items:
        for quality_brief, quality_item in quality_items:
            if delivery_item["release_target"] != quality_item["release_target"]:
                continue
            dependencies.append(
                {
                    "release_target": delivery_item["release_target"],
                    "delivery_agent_workspace_id": delivery_brief["agent_workspace_id"],
                    "delivery_task_id": delivery_item["id"],
                    "delivery_task_title": delivery_item["title"],
                    "delivery_task_status": delivery_item["status"],
                    "quality_agent_workspace_id": quality_brief["agent_workspace_id"],
                    "quality_item_id": quality_item["id"],
                    "quality_item_title": quality_item["title"],
                    "quality_item_severity": quality_item.get("severity"),
                    "quality_item_status": quality_item.get("quality_status"),
                    "quality_release_readiness": quality_brief.get("release_readiness"),
                }
            )

    data_gaps = list(briefs_result.data_gaps)
    if not dependencies:
        data_gaps.append(
            "No cross-workspace dependency found - no Delivery task and Quality work item currently share a release_target."
        )

    return ToolResult(
        status=ToolResultStatus.PARTIAL if data_gaps else ToolResultStatus.SUCCESS,
        payload={"dependencies": dependencies},
        data_gaps=tuple(data_gaps),
        sources=briefs_result.sources,
    )


async def build_executive_brief(db: AsyncSession, context: AgentContext) -> ToolResult:
    briefs_result = await get_workspace_briefs(db, context)
    briefs = briefs_result.payload["briefs"]
    data_gaps = list(briefs_result.data_gaps)

    facts: list[dict] = []
    risks: list[dict] = []
    decisions_needed: list[dict] = []
    workspace_brief_ids: list[str] = []
    for brief in briefs:
        workspace_brief_ids.append(brief["brief_id"])
        facts.extend(brief.get("facts", []))
        decisions_needed.extend(brief.get("decisions_needed", []))

    # Cross-workspace dependencies first (MULTI_AGENT_IMPLEMENTATION_PLAN.md Ngày 4) - a
    # release_target-matched pair produces a specific, named risk ("QA báo NOT_READY do critical
    # bug X, ảnh hưởng trực tiếp đến Delivery Y") instead of the generic per-brief fallback below.
    deps_result = await get_cross_workspace_dependencies(db, context)
    cross_workspace_dependencies = deps_result.payload["dependencies"]
    linked_quality_item_ids: set[str] = set()
    for dep in cross_workspace_dependencies:
        if dep["quality_release_readiness"] not in ("NOT_READY", "AT_RISK"):
            continue
        linked_quality_item_ids.add(dep["quality_item_id"])
        risks.append(
            {
                "text": (
                    f"QA báo {dep['quality_release_readiness']} do "
                    f"{'critical bug' if dep['quality_item_severity'] == 'critical' else 'work item'} "
                    f"\"{dep['quality_item_title']}\", ảnh hưởng trực tiếp đến Delivery "
                    f"\"{dep['delivery_task_title']}\" (release {dep['release_target']})."
                ),
                "severity": "high" if dep["quality_release_readiness"] == "NOT_READY" else "medium",
                "release_target": dep["release_target"],
                "delivery_task_id": dep["delivery_task_id"],
                "quality_item_id": dep["quality_item_id"],
            }
        )

    # Generic per-brief fallback risk - only for a NOT_READY/AT_RISK quality brief that had no
    # cross-workspace match above (avoids double-reporting the same brief as two separate risks).
    for brief in briefs:
        if brief["brief_type"] != "quality" or brief.get("release_readiness") not in ("NOT_READY", "AT_RISK"):
            continue
        brief_defect_ids = {item["id"] for item in brief.get("facts", [])}
        if brief_defect_ids & linked_quality_item_ids:
            continue
        risks.append(
            {
                "text": f"Release is {brief['release_readiness']} per the latest Quality brief.",
                "severity": "high" if brief["release_readiness"] == "NOT_READY" else "medium",
            }
        )

    if deps_result.data_gaps:
        data_gaps.extend(gap for gap in deps_result.data_gaps if gap not in data_gaps)

    if not workspace_brief_ids and not data_gaps:
        # ExecutiveBrief's own validator requires this - defensive, should be unreachable since
        # get_workspace_briefs always reports a data gap for a missing brief.
        data_gaps.append("No Delivery/Quality briefs are available yet.")

    headline = (
        f"{len(workspace_brief_ids)} workspace brief(s) tổng hợp"
        + (f", {len(risks)} risk cần chú ý" if risks else ", không có risk nổi bật")
        + "."
    )

    executive_brief = ExecutiveBrief(
        brief_id=f"executive-brief-{uuid4()}",
        trace_id=context.trace_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        generated_at=datetime.now(UTC),
        workspace_brief_ids=tuple(dict.fromkeys(workspace_brief_ids)),
        headline=headline,
        facts=tuple(facts),
        risks=tuple(risks),
        cross_workspace_dependencies=tuple(cross_workspace_dependencies),
        decisions_needed=tuple(decisions_needed),
        data_gaps=tuple(data_gaps),
    )

    return ToolResult(
        status=ToolResultStatus.PARTIAL if data_gaps else ToolResultStatus.SUCCESS,
        payload={"executive_brief": executive_brief.model_dump(mode="json")},
        data_gaps=tuple(data_gaps),
        sources=briefs_result.sources,
    )


async def get_my_calendar(db: AsyncSession, context: AgentContext, *, days_ahead: int = 7) -> ToolResult:
    """Read-only: the Executive's OWN personal calendar (per-user Google OAuth, same service the
    Personal Agent uses) - never a team/shared calendar. Not connecting Calendar is an honest data
    gap, not an error - this tool must not block the rest of an executive brief."""
    await _reverify(db, context)
    now = datetime.now(UTC)
    try:
        events = await calendar_service.list_events(
            context.actor.user_id, now.isoformat(), (now + timedelta(days=days_ahead)).isoformat()
        )
    except CalendarNotConnected:
        return ToolResult(
            status=ToolResultStatus.PARTIAL,
            payload={"events": []},
            data_gaps=("Executive has not connected Google Calendar.",),
        )
    return ToolResult(status=ToolResultStatus.SUCCESS, payload={"events": events})


async def propose_executive_meeting(
    db: AsyncSession,
    context: AgentContext,
    *,
    title: str,
    starts_at: datetime,
    attendee_ids: tuple[str, ...] = (),
) -> ToolResult:
    """Preview-only: draft an ActionProposal for an executive meeting. Never creates a calendar
    event - a human must confirm via src.agents.hitl_executor before this has any real effect."""
    await _reverify(db, context)

    now = datetime.now(UTC)
    draft_payload = {"title": title, "starts_at": starts_at.isoformat(), "attendee_ids": list(attendee_ids)}
    proposal = ActionProposal(
        proposal_id=f"executive-meeting-{uuid4()}",
        trace_id=context.trace_id,
        actor_user_id=context.actor.user_id,
        action="preview_executive_meeting",
        payload=draft_payload,
        payload_hash=action_payload_hash(draft_payload),
        idempotency_key=f"executive-meeting-{uuid4()}",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        payload={"proposal": proposal.model_dump(mode="json"), "requires_confirmation": True},
    )
