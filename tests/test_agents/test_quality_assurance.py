from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.generate_multi_agent_dataset import build_cases
from src.agents.contracts import AgentProfile, ReleaseReadiness
from src.agents.profiles.quality_assurance import (
    QUALITY_ASSURANCE_PROMPT_VERSION,
    QUALITY_ASSURANCE_SYSTEM_PROMPT,
    evaluate_release_readiness,
)
from src.agents.schemas.quality import (
    QualityReadinessAssessment,
    QualityReadinessReason,
    QualityTestProgress,
    QualityWorkItem,
    QualityWorkItemType,
)
from src.agents.tools.registry import get_profile_registration

ROOT = Path(__file__).resolve().parents[2]


def _item(
    item_id: str,
    *,
    item_type: str = "bug",
    severity: str = "medium",
    status: str = "open",
) -> QualityWorkItem:
    return QualityWorkItem(
        work_item_id=item_id,
        title=f"Quality item {item_id}",
        work_item_type=item_type,
        severity=severity,
        quality_status=status,
        source_id=f"source-{item_id}",
        release_id="release-1",
    )


def test_quality_metadata_contract_is_strict_and_frozen():
    item = _item("BUG-1", severity="critical")

    assert item.work_item_type == QualityWorkItemType.BUG
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        QualityWorkItem.model_validate({**item.model_dump(), "owner_guess": "someone"})
    with pytest.raises(ValidationError, match="Input should be"):
        QualityWorkItem.model_validate({**item.model_dump(), "severity": "urgent"})
    with pytest.raises(ValidationError, match="frozen"):
        item.quality_status = "passed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("items", "required_ids", "expected", "reason"),
    [
        (
            [_item("BUG-C", severity="critical", status="open")],
            [],
            ReleaseReadiness.NOT_READY,
            QualityReadinessReason.CRITICAL_DEFECT_ACTIVE,
        ),
        (
            [],
            ["CHECK-MISSING"],
            ReleaseReadiness.NOT_READY,
            QualityReadinessReason.REQUIRED_RELEASE_CHECK_MISSING,
        ),
        (
            [_item("CHECK-F", item_type="release_check", status="failed")],
            ["CHECK-F"],
            ReleaseReadiness.NOT_READY,
            QualityReadinessReason.REQUIRED_RELEASE_CHECK_FAILED,
        ),
        (
            [_item("BUG-H", severity="high", status="testing")],
            [],
            ReleaseReadiness.AT_RISK,
            QualityReadinessReason.NON_CRITICAL_DEFECT_ACTIVE,
        ),
        (
            [_item("TEST-B", item_type="test_case", status="blocked")],
            [],
            ReleaseReadiness.AT_RISK,
            QualityReadinessReason.TEST_FAILURE_OR_BLOCKER,
        ),
        (
            [_item("CHECK-T", item_type="release_check", status="testing")],
            ["CHECK-T"],
            ReleaseReadiness.AT_RISK,
            QualityReadinessReason.REQUIRED_RELEASE_CHECK_PENDING,
        ),
        (
            [_item("CHECK-P", item_type="release_check", status="passed")],
            ["CHECK-P"],
            ReleaseReadiness.READY,
            QualityReadinessReason.ALL_REQUIRED_CHECKS_PASSED,
        ),
    ],
)
def test_frozen_readiness_rule_matrix(items, required_ids, expected, reason):
    assessment = evaluate_release_readiness(items, required_release_check_ids=required_ids)

    assert assessment.release_readiness == expected
    assert reason in assessment.reasons


def test_ready_is_impossible_without_declared_required_release_checks():
    assessment = evaluate_release_readiness([], required_release_check_ids=[])

    assert assessment.release_readiness == ReleaseReadiness.AT_RISK
    assert assessment.data_gaps
    assert QualityReadinessReason.NO_REQUIRED_RELEASE_CHECKS_DECLARED in assessment.reasons


def test_ready_assessment_rejects_any_reported_data_gap():
    with pytest.raises(ValidationError, match="READY cannot be emitted"):
        QualityReadinessAssessment(
            release_readiness=ReleaseReadiness.READY,
            test_progress=QualityTestProgress(
                total=0,
                open=0,
                testing=0,
                passed=0,
                failed=0,
                blocked=0,
            ),
            reasons=(QualityReadinessReason.ALL_REQUIRED_CHECKS_PASSED,),
            data_gaps=("Required regression evidence is unavailable",),
        )


def test_required_release_check_id_cannot_point_to_a_bug():
    with pytest.raises(ValueError, match="must refer to release_check"):
        evaluate_release_readiness(
            [_item("BUG-1")],
            required_release_check_ids=["BUG-1"],
        )


def test_day_one_has_exactly_fifteen_quality_fixture_expectations():
    cases = [case for case in build_cases() if case["category"] == "quality_readiness"]

    assert [case["case_id"] for case in cases] == [f"QLT-{index:03d}" for index in range(1, 16)]
    for case in cases:
        resource = case["context"]["resources"][0]
        metadata = resource["metadata"]
        item = QualityWorkItem(
            work_item_id=resource["id"],
            title=case["title"],
            work_item_type=metadata["work_item_type"],
            severity=metadata["severity"],
            quality_status=metadata["quality_status"],
            source_id=resource["id"],
        )
        required_ids = [item.work_item_id] if item.work_item_type == QualityWorkItemType.RELEASE_CHECK else []

        assessment = evaluate_release_readiness(
            [item],
            required_release_check_ids=required_ids,
        )

        assert assessment.release_readiness.value == case["expected"]["release_readiness"]
        assert assessment.source_ids == tuple(case["expected"]["required_source_ids"])


def test_quality_profile_skeleton_matches_frozen_registry_and_guardrails():
    registration = get_profile_registration(AgentProfile.QUALITY_ASSURANCE)

    assert registration.prompt_version == QUALITY_ASSURANCE_PROMPT_VERSION
    assert "build_quality_brief" in registration.allowed_tools
    assert "raw Product Delivery conversations" in QUALITY_ASSURANCE_SYSTEM_PROMPT
    assert "human confirmation" in QUALITY_ASSURANCE_SYSTEM_PROMPT
    assert "source_ids" in QUALITY_ASSURANCE_SYSTEM_PROMPT


def test_quality_seven_day_report_document_exists():
    assert (ROOT / "docs" / "ROLE_C_QUALITY_ASSURANCE_7_DAY_PLAN.md").is_file()
