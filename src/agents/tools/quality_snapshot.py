from __future__ import annotations

import asyncio
from datetime import datetime

from src.agents.contracts import AgentContext, SourceReference, ToolResult, ToolResultStatus
from src.services.quality_workspace_service import (
    QualityWorkItemRepository,
    QualityWorkspaceError,
    load_quality_snapshot,
)


def _error_result(code: str, message: str) -> ToolResult:
    return ToolResult(
        status=ToolResultStatus.ERROR,
        error_code=code,
        error_message=message,
    )


async def get_quality_snapshot(
    *,
    context: AgentContext,
    repository: QualityWorkItemRepository,
    release_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    timeout_seconds: float = 10.0,
) -> ToolResult:
    """Return normalized QA work items from only the trusted context allowlist."""

    try:
        snapshot = await asyncio.wait_for(
            load_quality_snapshot(
                repository,
                context=context,
                release_id=release_id,
                period_start=period_start,
                period_end=period_end,
            ),
            timeout=max(0.01, min(timeout_seconds, 30.0)),
        )
    except TimeoutError:
        return _error_result("QUALITY_SNAPSHOT_TIMEOUT", "Quality snapshot retrieval timed out")
    except QualityWorkspaceError as exc:
        return _error_result(exc.code, "Quality snapshot access or validation failed")
    except Exception:
        return _error_result("QUALITY_SNAPSHOT_FAILED", "Quality snapshot retrieval failed")

    sources = tuple(
        SourceReference(
            resource_id=item.source_id,
            resource_type="quality_work_item",
            agent_workspace_id=snapshot.agent_workspace_id,
            classification="quality",
            captured_at=item.captured_at,
        )
        for item in snapshot.work_items
    )
    return ToolResult(
        status=ToolResultStatus.PARTIAL if snapshot.data_gaps else ToolResultStatus.SUCCESS,
        payload=snapshot.model_dump(mode="json", exclude={"data_gaps"}),
        sources=sources,
        data_gaps=snapshot.data_gaps,
    )
