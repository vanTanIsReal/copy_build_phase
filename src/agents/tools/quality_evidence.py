from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import AgentContext, SourceReference, ToolResult, ToolResultStatus
from src.services.quality_workspace_service import QualityWorkspaceError, search_scoped_quality_evidence


def _error_result(code: str, message: str) -> ToolResult:
    return ToolResult(
        status=ToolResultStatus.ERROR,
        error_code=code,
        error_message=message,
    )


async def search_quality_evidence(
    *,
    db: AsyncSession,
    context: AgentContext,
    query: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    limit: int = 20,
    timeout_seconds: float = 10.0,
) -> ToolResult:
    """Search linked QA group messages after current membership and consent revalidation."""

    try:
        evidence = await asyncio.wait_for(
            search_scoped_quality_evidence(
                db,
                context=context,
                query=query,
                period_start=period_start,
                period_end=period_end,
                limit=limit,
            ),
            timeout=max(0.01, min(timeout_seconds, 30.0)),
        )
    except TimeoutError:
        return _error_result("QUALITY_EVIDENCE_TIMEOUT", "Quality evidence search timed out")
    except QualityWorkspaceError as exc:
        return _error_result(exc.code, "Quality evidence access or validation failed")
    except Exception:
        return _error_result("QUALITY_EVIDENCE_FAILED", "Quality evidence search failed")

    captured_at_by_source: dict[str, datetime] = {}
    for excerpt in evidence.excerpts:
        previous = captured_at_by_source.get(excerpt.source_id)
        if previous is None or excerpt.captured_at > previous:
            captured_at_by_source[excerpt.source_id] = excerpt.captured_at
    sources = tuple(
        SourceReference(
            resource_id=source_id,
            resource_type="quality_conversation",
            agent_workspace_id=evidence.agent_workspace_id,
            classification="quality",
            captured_at=captured_at,
        )
        for source_id, captured_at in captured_at_by_source.items()
    )
    return ToolResult(
        status=ToolResultStatus.PARTIAL if evidence.data_gaps else ToolResultStatus.SUCCESS,
        payload=evidence.model_dump(mode="json", exclude={"data_gaps"}),
        sources=sources,
        data_gaps=evidence.data_gaps,
    )
