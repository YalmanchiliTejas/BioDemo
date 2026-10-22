from __future__ import annotations

from benchmarks.common.metric_registry import precision_recall


def score_identity(predicted_ids: set[str], visible_ids: set[str]) -> dict:
    scores = precision_recall(predicted_ids, visible_ids)
    return {"entity_precision": scores["precision"], "entity_recall": scores["recall"],
            "future_id_leakage": len(predicted_ids-visible_ids)}
