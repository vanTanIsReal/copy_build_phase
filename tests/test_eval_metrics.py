import pytest

from scripts.eval_metrics import EvalObservation, calculate_metrics


def test_calculate_metrics_covers_quality_reliability_and_latency():
    metrics = calculate_metrics(
        [
            EvalObservation(2, 0, 0, 100, True),
            EvalObservation(1, 1, 1, 200, True),
            EvalObservation(0, 0, 1, 1000, False),
        ]
    )

    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["recall"] == pytest.approx(0.6)
    assert metrics["f1"] == pytest.approx(2 / 3)
    assert metrics["exact_match_rate"] == pytest.approx(1 / 3)
    assert metrics["valid_output_rate"] == pytest.approx(2 / 3)
    assert metrics["latency_mean_ms"] == pytest.approx(1300 / 3)
    assert metrics["latency_p50_ms"] == 200
    assert metrics["latency_p95_ms"] == 1000


def test_empty_evaluation_is_safe():
    metrics = calculate_metrics([])

    assert metrics["total_cases"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["exact_match_rate"] == 0.0
    assert metrics["latency_p95_ms"] == 0.0
