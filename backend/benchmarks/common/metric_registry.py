from __future__ import annotations

from math import sqrt


METRIC_DEFINITIONS = {
    "entity_precision": "correct recovered canonical IDs / all recovered IDs",
    "entity_recall": "correct recovered canonical IDs / visible canonical IDs",
    "critical_evidence_recall": "recovered critical evidence IDs / visible critical evidence IDs",
    "source_grounding_fraction": "source-located rows with a visible canonical ID / source-located rows",
    "future_id_leakage": "recovered IDs unavailable at the task cutoff",
    "time_zero_match_fraction": "matching raw/aligned values at inoculation / comparable pairs",
}


def precision_recall(predicted: set[str], expected: set[str]) -> dict[str, float | None]:
    correct = len(predicted & expected)
    return {"precision": correct/len(predicted) if predicted else None,
            "recall": correct/len(expected) if expected else None}


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson interval for Bernoulli observations; not used for deterministic replay stability."""
    if trials <= 0:
        return None
    p = successes/trials
    denominator = 1 + z*z/trials
    center = (p + z*z/(2*trials))/denominator
    radius = z*sqrt((p*(1-p)+z*z/(4*trials))/trials)/denominator
    return max(0, center-radius), min(1, center+radius)
