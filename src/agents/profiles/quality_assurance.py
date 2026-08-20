from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from src.agents.contracts import ReleaseReadiness
from src.agents.schemas.quality import (
    QualityItemFinding,
    QualityReadinessAssessment,
    QualityReadinessReason,
    QualityStatus,
    QualityTestProgress,
    QualityWorkItem,
    QualityWorkItemType,
)

QUALITY_ASSURANCE_PROMPT_VERSION = "quality-assurance-v1"

QUALITY_ASSURANCE_SYSTEM_PROMPT = """You are the Quality Assurance Agent.
Use only source-backed bug, test-case, and release-check facts in the authorized Quality workspace.
Apply the deterministic readiness result supplied by code; never soften or override it.
An active critical defect, a missing required release check, or a failed/blocked required release check
makes the release NOT_READY. Unresolved non-critical defects, failed/blocked tests, or pending required
checks make it AT_RISK. READY requires every declared required release check to be present and passed,
with no unresolved defect or failed/blocked test.
Do not read raw Product Delivery conversations; use only structured release/dependency references.
Do not lower severity, close work items, schedule meetings, or send reminders. Side effects must be
returned as proposals for policy evaluation and human confirmation.
Every factual claim must cite source_ids. Report missing evidence as data_gaps and never invent it.
"""


_ACTIVE_DEFECT_STATUSES = {
    QualityStatus.OPEN,
    QualityStatus.TESTING,
    QualityStatus.FAILED,
    QualityStatus.BLOCKED,
}
_FAILED_OR_BLOCKED = {QualityStatus.FAILED, QualityStatus.BLOCKED}
_PENDING = {QualityStatus.OPEN, QualityStatus.TESTING}


def _finding(item: QualityWorkItem) -> QualityItemFinding:
    return QualityItemFinding(
        work_item_id=item.work_item_id,
        title=item.title,
        severity=item.severity,
        quality_status=item.quality_status,
        source_id=item.source_id,
    )


def evaluate_release_readiness(
    work_items: Iterable[QualityWorkItem],
    *,
    required_release_check_ids: Iterable[str],
) -> QualityReadinessAssessment:
    """Apply the frozen Day-1 release-readiness rules without LLM judgment."""

    items = tuple(work_items)
    required_ids = tuple(dict.fromkeys(required_release_check_ids))
    item_by_id = {item.work_item_id: item for item in items}
    if len(item_by_id) != len(items):
        raise ValueError("Quality work_item_id values must be unique")

    source_ids = tuple(dict.fromkeys(item.source_id for item in items))
    test_items = tuple(
        item
        for item in items
        if item.work_item_type in {QualityWorkItemType.TEST_CASE, QualityWorkItemType.RELEASE_CHECK}
    )
    status_counts = Counter(item.quality_status for item in test_items)
    progress = QualityTestProgress(
        total=len(test_items),
        open=status_counts[QualityStatus.OPEN],
        testing=status_counts[QualityStatus.TESTING],
        passed=status_counts[QualityStatus.PASSED],
        failed=status_counts[QualityStatus.FAILED],
        blocked=status_counts[QualityStatus.BLOCKED],
    )

    active_defects = tuple(
        item
        for item in items
        if item.work_item_type == QualityWorkItemType.BUG and item.quality_status in _ACTIVE_DEFECT_STATUSES
    )
    critical_defects = tuple(item for item in active_defects if item.severity == "critical")
    non_critical_defects = tuple(item for item in active_defects if item.severity != "critical")
    blocked_tests = tuple(item for item in test_items if item.quality_status in _FAILED_OR_BLOCKED)

    missing_required_ids = tuple(check_id for check_id in required_ids if check_id not in item_by_id)
    required_checks = tuple(item_by_id[check_id] for check_id in required_ids if check_id in item_by_id)
    wrong_type_required_ids = tuple(
        item.work_item_id for item in required_checks if item.work_item_type != QualityWorkItemType.RELEASE_CHECK
    )
    if wrong_type_required_ids:
        joined = ", ".join(wrong_type_required_ids)
        raise ValueError(f"Required release check IDs must refer to release_check items: {joined}")

    failed_required = tuple(item for item in required_checks if item.quality_status in _FAILED_OR_BLOCKED)
    pending_required = tuple(item for item in required_checks if item.quality_status in _PENDING)
    reasons: list[QualityReadinessReason] = []
    data_gaps: list[str] = []

    if critical_defects:
        reasons.append(QualityReadinessReason.CRITICAL_DEFECT_ACTIVE)
    if missing_required_ids:
        reasons.append(QualityReadinessReason.REQUIRED_RELEASE_CHECK_MISSING)
        data_gaps.append("Missing required release checks: " + ", ".join(missing_required_ids))
    if failed_required:
        reasons.append(QualityReadinessReason.REQUIRED_RELEASE_CHECK_FAILED)

    if reasons:
        readiness = ReleaseReadiness.NOT_READY
    else:
        if pending_required:
            reasons.append(QualityReadinessReason.REQUIRED_RELEASE_CHECK_PENDING)
        if non_critical_defects:
            reasons.append(QualityReadinessReason.NON_CRITICAL_DEFECT_ACTIVE)
        if blocked_tests:
            reasons.append(QualityReadinessReason.TEST_FAILURE_OR_BLOCKER)
        if not required_ids:
            reasons.append(QualityReadinessReason.NO_REQUIRED_RELEASE_CHECKS_DECLARED)
            data_gaps.append("No required release checks were declared for this assessment")

        if reasons:
            readiness = ReleaseReadiness.AT_RISK
        else:
            reasons.append(QualityReadinessReason.ALL_REQUIRED_CHECKS_PASSED)
            readiness = ReleaseReadiness.READY

    quality_risk_items = tuple(dict.fromkeys((*non_critical_defects, *pending_required)))
    return QualityReadinessAssessment(
        release_readiness=readiness,
        test_progress=progress,
        critical_defects=tuple(_finding(item) for item in critical_defects),
        blocked_tests=tuple(_finding(item) for item in blocked_tests),
        quality_risks=tuple(_finding(item) for item in quality_risk_items),
        reasons=tuple(reasons),
        data_gaps=tuple(data_gaps),
        source_ids=source_ids,
    )
