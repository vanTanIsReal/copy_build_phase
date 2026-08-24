from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import (
    AgentContext,
    AgentProfile,
    BusinessRole,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
)
from src.agents.policies.scope_resolver import resolve_agent_scope
from src.agents.schemas.quality import (
    QualityEvidence,
    QualityEvidenceExcerpt,
    QualitySnapshot,
    QualitySnapshotItem,
    QualityStatus,
    QualityTestProgress,
    QualityWorkItemType,
)
from src.db.models import AgentWorkspaceConversation, Conversation, Message, Task


class QualityWorkspaceError(RuntimeError):
    """Expected service failure safe to normalize at the tool boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class QualityQueryScope(BaseModel):
    """Explicit scope passed to every repository query; there is no company-wide default."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_workspace_id: str = Field(min_length=1)
    agent_workspace_id: str = Field(min_length=1)
    allowed_resource_ids: tuple[str, ...]
    consent_scope_hash: str | None = None


class QualityWorkItemRepository(Protocol):
    async def list_scoped(
        self,
        *,
        scope: QualityQueryScope,
        release_id: str | None,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> Sequence[QualitySnapshotItem]: ...


class InMemoryQualityWorkItemRepository:
    """Fixture adapter used until the shared scoped work-item query is available."""

    def __init__(self, records: Sequence[QualitySnapshotItem]):
        self._records = tuple(records)

    async def list_scoped(
        self,
        *,
        scope: QualityQueryScope,
        release_id: str | None,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> Sequence[QualitySnapshotItem]:
        if not scope.allowed_resource_ids:
            return ()
        allowed_ids = set(scope.allowed_resource_ids)
        return tuple(
            record
            for record in self._records
            if record.organization_workspace_id == scope.organization_workspace_id
            and record.agent_workspace_id == scope.agent_workspace_id
            and record.source_id in allowed_ids
            and (release_id is None or record.release_id == release_id)
            and (period_start is None or record.captured_at >= period_start)
            and (period_end is None or record.captured_at <= period_end)
        )


def quality_scope_from_context(context: AgentContext) -> QualityQueryScope:
    target_workspace_id = context.request.target_agent_workspace_id
    if (
        context.authorization.decision != PolicyDecision.ALLOW
        or context.authorization.reason != PolicyReason.ALLOWED
        or context.runtime.agent_profile != AgentProfile.QUALITY_ASSURANCE
        or context.request.requested_scope != RequestedScope.WORKSPACE
        or context.request.intent.value not in {"quality_readiness", "quality_brief"}
        or context.actor.business_role not in {BusinessRole.LEAD, BusinessRole.MEMBER}
        or not target_workspace_id
        or target_workspace_id not in context.authorization.allowed_agent_workspace_ids
        or target_workspace_id not in context.actor.agent_workspace_ids
    ):
        raise QualityWorkspaceError("ACCESS_DENIED")
    return QualityQueryScope(
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_workspace_id=target_workspace_id,
        allowed_resource_ids=context.authorization.allowed_resource_ids,
        consent_scope_hash=context.authorization.consent_scope_hash,
    )


async def revalidate_quality_scope(db: AsyncSession, context: AgentContext) -> QualityQueryScope:
    original_scope = quality_scope_from_context(context)
    current = await resolve_agent_scope(
        db,
        user_id=context.actor.user_id,
        organization_workspace_id=original_scope.organization_workspace_id,
        agent_profile=AgentProfile.QUALITY_ASSURANCE,
        requested_scope=RequestedScope.WORKSPACE,
        target_agent_workspace_id=original_scope.agent_workspace_id,
    )
    if current.decision != PolicyDecision.ALLOW:
        raise QualityWorkspaceError("ACCESS_DENIED")
    if current.consent_scope_hash != original_scope.consent_scope_hash:
        raise QualityWorkspaceError("CONSENT_CHANGED")
    if original_scope.agent_workspace_id not in current.allowed_agent_workspace_ids:
        raise QualityWorkspaceError("ACCESS_DENIED")
    return original_scope.model_copy(update={"allowed_resource_ids": current.allowed_resource_ids})


def _validate_period(period_start: datetime | None, period_end: datetime | None) -> None:
    for value in (period_start, period_end):
        if value is not None and value.tzinfo is None:
            raise QualityWorkspaceError("INVALID_TIME_RANGE")
    if period_start is not None and period_end is not None and period_end < period_start:
        raise QualityWorkspaceError("INVALID_TIME_RANGE")


def _test_progress(items: Sequence[QualitySnapshotItem]) -> QualityTestProgress:
    test_items = tuple(
        item
        for item in items
        if item.work_item_type in {QualityWorkItemType.TEST_CASE, QualityWorkItemType.RELEASE_CHECK}
    )
    counts = Counter(item.quality_status for item in test_items)
    return QualityTestProgress(
        total=len(test_items),
        open=counts[QualityStatus.OPEN],
        testing=counts[QualityStatus.TESTING],
        passed=counts[QualityStatus.PASSED],
        failed=counts[QualityStatus.FAILED],
        blocked=counts[QualityStatus.BLOCKED],
    )


async def load_quality_snapshot(
    repository: QualityWorkItemRepository,
    *,
    context: AgentContext,
    release_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> QualitySnapshot:
    scope = quality_scope_from_context(context)
    _validate_period(period_start, period_end)
    items = tuple(
        await repository.list_scoped(
            scope=scope,
            release_id=release_id,
            period_start=period_start,
            period_end=period_end,
        )
    )
    if any(
        item.organization_workspace_id != scope.organization_workspace_id
        or item.agent_workspace_id != scope.agent_workspace_id
        or item.source_id not in scope.allowed_resource_ids
        for item in items
    ):
        raise QualityWorkspaceError("REPOSITORY_SCOPE_VIOLATION")
    gaps = () if items else ("No authorized Quality work items matched the requested scope",)
    return QualitySnapshot(
        agent_workspace_id=scope.agent_workspace_id,
        work_items=items,
        test_progress=_test_progress(items),
        generated_at=datetime.now(UTC),
        freshest_source_at=max((item.captured_at for item in items), default=None),
        data_gaps=gaps,
    )


async def list_quality_work_items(db: AsyncSession, agent_workspace_id: str) -> list[Task]:
    """Real (Postgres-backed) read of QA work items - bugs/test cases/release checks - scoped to
    one quality_assurance AgentWorkspace. Mirrors delivery_workspace_service.list_tasks's decision
    to reuse Task (Task.work_item_type/severity/quality_status/release_target, added specifically
    for this purpose - see src/db/models.py's Task docstring) rather than a parallel work-item
    table. Callers are expected to have already run
    resource_guard.enforce_agent_workspace_access(agent_workspace_id=...) before calling this,
    same convention as every delivery_workspace_service function (G2).

    Deliberately does NOT go through QualityWorkItemRepository/load_quality_snapshot above: that
    protocol's REPOSITORY_SCOPE_VIOLATION check requires every item's source_id to be one of
    scope.allowed_resource_ids (linked QA *conversation* IDs - see
    scope_resolver._resolve_conversation_resources), which fits evidence extracted from QA chat
    but not a freestanding Task row. Task-backed work items use the coarser
    enforce_agent_workspace_access boundary instead, exactly like Delivery's own Task reads.
    """
    stmt = (
        select(Task)
        .where(Task.agent_workspace_id == agent_workspace_id, Task.work_item_type.is_not(None))
        .order_by(Task.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _as_aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def search_scoped_quality_evidence(
    db: AsyncSession,
    *,
    context: AgentContext,
    query: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    limit: int = 20,
) -> QualityEvidence:
    normalized_query = query.strip()
    if not normalized_query or len(normalized_query) > 500:
        raise QualityWorkspaceError("INVALID_QUERY")
    _validate_period(period_start, period_end)
    scope = await revalidate_quality_scope(db, context)
    safe_limit = max(1, min(limit, 50))
    if not scope.allowed_resource_ids:
        return QualityEvidence(
            agent_workspace_id=scope.agent_workspace_id,
            query=normalized_query,
            generated_at=datetime.now(UTC),
            data_gaps=("No linked, consent-enabled Quality conversation is available",),
        )

    statement = (
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(
            AgentWorkspaceConversation,
            AgentWorkspaceConversation.conversation_id == Conversation.id,
        )
        .where(
            AgentWorkspaceConversation.agent_workspace_id == scope.agent_workspace_id,
            AgentWorkspaceConversation.classification == "quality",
            Conversation.workspace_id == scope.organization_workspace_id,
            Conversation.type == "group",
            Conversation.ai_enabled.is_(True),
            Conversation.id.in_(scope.allowed_resource_ids),
            Message.content.ilike(f"%{_escape_ilike(normalized_query)}%", escape="\\"),
        )
    )
    if period_start is not None:
        statement = statement.where(Message.created_at >= period_start)
    if period_end is not None:
        statement = statement.where(Message.created_at <= period_end)
    rows = tuple(
        (await db.execute(statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(safe_limit)))
        .scalars()
        .all()
    )
    excerpts = tuple(
        QualityEvidenceExcerpt(
            message_id=message.id,
            source_id=message.conversation_id,
            excerpt=message.content[:1000],
            captured_at=_as_aware_utc(message.created_at),
        )
        for message in reversed(rows)
    )
    gaps = () if excerpts else ("No authorized Quality evidence matched the query",)
    return QualityEvidence(
        agent_workspace_id=scope.agent_workspace_id,
        query=normalized_query,
        excerpts=excerpts,
        generated_at=datetime.now(UTC),
        freshest_source_at=max((excerpt.captured_at for excerpt in excerpts), default=None),
        data_gaps=gaps,
    )
