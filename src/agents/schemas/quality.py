from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from src.agents.contracts import FrozenContract, ReleaseReadiness


class QualityWorkItemType(StrEnum):
    BUG = "bug"
    TEST_CASE = "test_case"
    RELEASE_CHECK = "release_check"


class QualitySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QualityStatus(StrEnum):
    OPEN = "open"
    TESTING = "testing"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class QualityReadinessReason(StrEnum):
    CRITICAL_DEFECT_ACTIVE = "critical_defect_active"
    REQUIRED_RELEASE_CHECK_MISSING = "required_release_check_missing"
    REQUIRED_RELEASE_CHECK_FAILED = "required_release_check_failed"
    REQUIRED_RELEASE_CHECK_PENDING = "required_release_check_pending"
    NON_CRITICAL_DEFECT_ACTIVE = "non_critical_defect_active"
    TEST_FAILURE_OR_BLOCKER = "test_failure_or_blocker"
    NO_REQUIRED_RELEASE_CHECKS_DECLARED = "no_required_release_checks_declared"
    ALL_REQUIRED_CHECKS_PASSED = "all_required_checks_passed"


class QualityWorkItem(FrozenContract):
    """Source-backed MVP representation of a bug, test case or release check."""

    work_item_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    work_item_type: QualityWorkItemType
    severity: QualitySeverity
    quality_status: QualityStatus
    source_id: str = Field(min_length=1)
    release_id: str | None = None


class QualityTestProgress(FrozenContract):
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    testing: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    blocked: int = Field(ge=0)

    @model_validator(mode="after")
    def status_counts_match_total(self) -> QualityTestProgress:
        status_total = self.open + self.testing + self.passed + self.failed + self.blocked
        if status_total != self.total:
            raise ValueError("Quality test status counts must add up to total")
        return self


class QualityItemFinding(FrozenContract):
    work_item_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    severity: QualitySeverity
    quality_status: QualityStatus
    source_id: str = Field(min_length=1)


class QualityReadinessAssessment(FrozenContract):
    """Validated Day-1 readiness output; WorkspaceBrief wrapping is a later slice."""

    release_readiness: ReleaseReadiness
    test_progress: QualityTestProgress
    critical_defects: tuple[QualityItemFinding, ...] = ()
    blocked_tests: tuple[QualityItemFinding, ...] = ()
    quality_risks: tuple[QualityItemFinding, ...] = ()
    reasons: tuple[QualityReadinessReason, ...]
    data_gaps: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def assessment_has_consistent_evidence(self) -> QualityReadinessAssessment:
        if not self.reasons:
            raise ValueError("A readiness assessment requires at least one reason")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("Readiness reasons must be unique")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must be unique")
        finding_source_ids = {
            finding.source_id
            for findings in (self.critical_defects, self.blocked_tests, self.quality_risks)
            for finding in findings
        }
        if not finding_source_ids.issubset(self.source_ids):
            raise ValueError("Every finding must reference an assessment source_id")
        if self.release_readiness == ReleaseReadiness.READY and self.data_gaps:
            raise ValueError("READY cannot be emitted while readiness data gaps remain")
        return self


class QualitySnapshotItem(FrozenContract):
    """Normalized, source-backed record returned by a scoped Quality repository."""

    work_item_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    work_item_type: QualityWorkItemType
    severity: QualitySeverity
    quality_status: QualityStatus
    source_id: str = Field(min_length=1)
    agent_workspace_id: str = Field(min_length=1)
    organization_workspace_id: str = Field(min_length=1)
    captured_at: datetime
    release_id: str | None = None
    owner_display_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def captured_at_is_timezone_aware(self) -> QualitySnapshotItem:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return self

    def as_work_item(self) -> QualityWorkItem:
        return QualityWorkItem(
            work_item_id=self.work_item_id,
            title=self.title,
            work_item_type=self.work_item_type,
            severity=self.severity,
            quality_status=self.quality_status,
            source_id=self.source_id,
            release_id=self.release_id,
        )


class QualitySnapshot(FrozenContract):
    agent_workspace_id: str = Field(min_length=1)
    work_items: tuple[QualitySnapshotItem, ...] = ()
    test_progress: QualityTestProgress
    generated_at: datetime
    freshest_source_at: datetime | None = None
    data_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def snapshot_is_consistent(self) -> QualitySnapshot:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        if self.freshest_source_at is not None and self.freshest_source_at.tzinfo is None:
            raise ValueError("freshest_source_at must include a timezone")
        if any(item.agent_workspace_id != self.agent_workspace_id for item in self.work_items):
            raise ValueError("Every snapshot item must belong to the scoped agent workspace")
        expected_total = sum(
            item.work_item_type in {QualityWorkItemType.TEST_CASE, QualityWorkItemType.RELEASE_CHECK}
            for item in self.work_items
        )
        if self.test_progress.total != expected_total:
            raise ValueError("test_progress total must match snapshot test and release-check items")
        return self


class QualityEvidenceExcerpt(FrozenContract):
    message_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=1000)
    captured_at: datetime

    @model_validator(mode="after")
    def evidence_timestamp_is_timezone_aware(self) -> QualityEvidenceExcerpt:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return self


class QualityEvidence(FrozenContract):
    agent_workspace_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=500)
    excerpts: tuple[QualityEvidenceExcerpt, ...] = ()
    generated_at: datetime
    freshest_source_at: datetime | None = None
    data_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_timestamps_are_timezone_aware(self) -> QualityEvidence:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        if self.freshest_source_at is not None and self.freshest_source_at.tzinfo is None:
            raise ValueError("freshest_source_at must include a timezone")
        return self
