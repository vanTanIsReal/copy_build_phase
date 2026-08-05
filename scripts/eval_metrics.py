"""Dependency-free metrics shared by agent evaluation scripts."""

from dataclasses import asdict, dataclass
from math import ceil


@dataclass(frozen=True)
class EvalObservation:
    """Measurements collected for one agent invocation."""

    true_positives: int
    false_positives: int
    false_negatives: int
    latency_ms: float
    valid_output: bool = True

    @property
    def exact_match(self) -> bool:
        return self.valid_output and self.false_positives == 0 and self.false_negatives == 0


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def _percentile(values: list[float], percentile: float) -> float:
    """Return the nearest-rank percentile, suitable for small eval datasets."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def calculate_metrics(observations: list[EvalObservation]) -> dict[str, int | float]:
    """Aggregate quality, reliability, and performance metrics.

    Rates are returned in the 0..1 range so callers can format them for either
    machine-readable JSON or human-readable percentages.
    """
    total_cases = len(observations)
    tp = sum(item.true_positives for item in observations)
    fp = sum(item.false_positives for item in observations)
    fn = sum(item.false_negatives for item in observations)
    precision = _safe_div(tp, tp + fp, default=1.0)
    recall = _safe_div(tp, tp + fn, default=1.0)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    latencies = [item.latency_ms for item in observations]

    return {
        "total_cases": total_cases,
        "passed_cases": sum(item.exact_match for item in observations),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_match_rate": _safe_div(sum(item.exact_match for item in observations), total_cases),
        "valid_output_rate": _safe_div(sum(item.valid_output for item in observations), total_cases),
        "latency_mean_ms": _safe_div(sum(latencies), total_cases),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def observation_to_dict(observation: EvalObservation) -> dict[str, int | float | bool]:
    return {**asdict(observation), "exact_match": observation.exact_match}
