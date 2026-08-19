from __future__ import annotations

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
