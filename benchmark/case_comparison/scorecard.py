"""Metric rows and improvement calculation for the comparison scorecard.

Values are always supplied by the case modules from recorded artifacts. This
module only formats them and computes absolute / percentage improvements when
both sides carry a numeric value. Missing values stay missing: no placeholder
numbers are produced.
"""

from __future__ import annotations

from typing import Any

# Evidence classification vocabulary used across both case studies.
VERIFIED = "verified"
OBSERVED = "observed"
MODELED = "modeled"
PREDICTED = "predicted"
NOT_MEASURED = "not_measured"

CLASSIFICATIONS = (VERIFIED, OBSERVED, MODELED, PREDICTED, NOT_MEASURED)

CLASSIFICATION_LABELS = {
    VERIFIED: "Verified",
    OBSERVED: "Observed",
    MODELED: "Modeled",
    PREDICTED: "Predicted",
    NOT_MEASURED: "Not measured",
}

CLASSIFICATION_DEFINITIONS = {
    VERIFIED: "Checked against an independent ground truth or the published source.",
    OBSERVED: "Directly measured in the dataset or recorded in execution logs.",
    MODELED: "Produced by the documented simulation or workflow assumptions.",
    PREDICTED: "Estimated by a model and not experimentally confirmed.",
    NOT_MEASURED: "No recorded benchmark output supports this value.",
}

DIRECTION_GLYPHS = {"better": "▲", "worse": "▼", "equal": "="}


def delta(
    traditional: float | None,
    ai: float | None,
    direction: str,
    *,
    tolerance: float = 1e-9,
) -> dict[str, Any] | None:
    """Absolute and relative change of the AI value against the traditional value.

    ``direction`` is ``"lower"`` or ``"higher"``: the direction in which the
    metric improves. A percentage is only produced when the traditional value
    is a non-zero number.
    """
    if direction not in {"lower", "higher"}:
        raise ValueError("direction must be 'lower' or 'higher'")
    if traditional is None or ai is None:
        return None
    change = ai - traditional
    improved = (change < 0) if direction == "lower" else (change > 0)
    if abs(change) <= tolerance:
        verdict = "equal"
    else:
        verdict = "better" if improved else "worse"
    percent = None
    if abs(traditional) > tolerance:
        percent = round(change / abs(traditional) * 100.0, 2)
    improvement_percent = None
    if percent is not None:
        improvement_percent = round(-percent, 2) if direction == "lower" else percent
    return {
        "absolute_change": round(change, 6),
        "relative_percent_change": percent,
        "improvement_percent": improvement_percent,
        "verdict": verdict,
        "glyph": DIRECTION_GLYPHS[verdict],
        "direction": direction,
    }


def side(
    value: float | None,
    *,
    display: str | None = None,
    classification: str = NOT_MEASURED,
    detail: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"unknown classification: {classification}")
    if value is None and classification != NOT_MEASURED and display is None:
        # A non-measured side must be explicit; never silently drop a value.
        raise ValueError("measured sides need a value or a display string")
    return {
        "value": value,
        "display": display if display is not None else ("Not measured" if value is None else str(value)),
        "classification": classification,
        "classification_label": CLASSIFICATION_LABELS[classification],
        "detail": detail,
        "unit": unit,
        "available": value is not None or classification != NOT_MEASURED,
    }


def not_measured(reason: str) -> dict[str, Any]:
    return side(None, display="Not measured", classification=NOT_MEASURED, detail=reason)


def metric(
    *,
    id: str,
    label: str,
    group: str,
    definition: str,
    traditional: dict[str, Any],
    ai: dict[str, Any],
    direction: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    computed = None
    if direction in {"lower", "higher"}:
        computed = delta(traditional.get("value"), ai.get("value"), direction)
    return {
        "id": id,
        "label": label,
        "group": group,
        "definition": definition,
        "traditional": traditional,
        "ai": ai,
        "delta": computed,
        "sources": sources or [],
        "note": note,
    }


def percent_side(value: float | None, *, classification: str = MODELED, digits: int = 1, detail: str | None = None) -> dict[str, Any]:
    if value is None:
        return not_measured(detail or "The recorded benchmark output does not contain this value.")
    return side(round(value, 6), display=f"{value * 100:.{digits}f}%", classification=classification, detail=detail)


def count_side(count: int | None, total: int | None, *, classification: str = MODELED, unit: str = "of", detail: str | None = None) -> dict[str, Any]:
    if count is None:
        return not_measured(detail or "The recorded benchmark output does not contain this value.")
    count = int(count)
    total = int(total) if total is not None else None
    display = f"{count}/{total}" if total is not None else str(count)
    value = count / total if total else None
    return side(value, display=display, classification=classification, detail=detail, unit=unit)


def hours_side(value: float | None, *, classification: str = MODELED, detail: str | None = None) -> dict[str, Any]:
    if value is None:
        return not_measured(detail or "The recorded benchmark output does not contain this value.")
    return side(round(value, 4), display=_format_duration_hours(value), classification=classification, detail=detail, unit="hours")


def seconds_side(value: float | None, *, classification: str = OBSERVED, detail: str | None = None) -> dict[str, Any]:
    if value is None:
        return not_measured(detail or "The recorded benchmark output does not contain this value.")
    return side(round(value, 3), display=f"{value:.3f} s", classification=classification, detail=detail, unit="seconds")


def _format_duration_hours(hours: float) -> str:
    if hours >= 48:
        return f"{hours / 24:.1f} days ({hours:.1f} h)"
    if hours >= 1:
        return f"{hours:.2f} h"
    return f"{hours * 60:.1f} min"


def format_duration_seconds(seconds: float) -> str:
    if seconds >= 86400:
        return f"{seconds / 86400:.1f} days"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"
