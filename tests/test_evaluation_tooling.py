import csv
from pathlib import Path

import pytest

from scripts.benchmark_api_latency import percentile, summarize_latencies
from scripts.run_coverage import build_command
from scripts.summarize_user_feedback import load_responses, summarize
from scripts.validate_agent_dataset import DEFAULT_DATASET, load_and_validate

ROOT = Path(__file__).resolve().parents[1]


def test_latency_percentiles_use_linear_interpolation():
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0.5) == 25.0
    assert percentile(values, 0.95) == pytest.approx(38.5)
    assert summarize_latencies(values)["p99_ms"] == pytest.approx(39.7)


def test_latency_percentile_rejects_empty_input():
    with pytest.raises(ValueError, match="empty sample"):
        percentile([], 0.95)


def test_coverage_command_enforces_local_source_gate():
    command = build_command(60)

    assert "--cov=src" in command
    assert "--cov-branch" in command
    assert "--cov-fail-under=60" in command
    assert any(argument.endswith("coverage-latest.json") for argument in command)
    assert any(argument.endswith("test-results.junit.xml") for argument in command)


def test_formal_agent_dataset_is_valid_non_empty_and_unique():
    dataset, errors = load_and_validate(DEFAULT_DATASET)
    cases = dataset["evaluation_cases"]

    assert errors == []
    assert len(cases) >= 15
    assert len({case["id"] for case in cases}) == len(cases)


def test_empty_feedback_is_pending_not_a_fake_pass():
    assert summarize([], minimum_participants=5) == {
        "status": "PENDING",
        "participant_count": 0,
        "response_count": 0,
        "minimum_participants": 5,
    }


def test_feedback_csv_is_validated_and_aggregated(tmp_path):
    path = tmp_path / "feedback.csv"
    fieldnames = [
        "response_id",
        "participant_id",
        "tested_at",
        "role",
        "scenario",
        "task_completed",
        "rating_1_5",
        "helpfulness_1_5",
        "trust_1_5",
        "would_use_again",
        "issue_category",
        "comment",
        "consent_to_use_anonymized_quote",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "response_id": "r-1",
                "participant_id": "p-1",
                "tested_at": "2026-08-25",
                "role": "employee",
                "scenario": "summary",
                "task_completed": "true",
                "rating_1_5": "4",
                "helpfulness_1_5": "5",
                "trust_1_5": "4",
                "would_use_again": "true",
                "issue_category": "none",
                "comment": "Hữu ích",
                "consent_to_use_anonymized_quote": "false",
            }
        )

    report = summarize(load_responses(path), minimum_participants=1)

    assert report["status"] == "READY"
    assert report["task_completion_rate"] == 1.0
    assert report["rating_mean"] == 4.0
    assert report["consented_anonymized_quotes"] == []


def test_evaluation_example_has_no_committed_secret():
    values = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value

    assert values["E2E_USER_EMAIL"] == ""
    assert values["E2E_USER_PASSWORD"] == ""
    assert values["RENDER_API_KEY"] == ""
    assert values["VERCEL_TOKEN"] == ""
