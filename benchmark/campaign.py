from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import BatchPlan, ProcessLimits


@dataclass(frozen=True)
class CampaignDefinition:
    campaign_id: str
    duration_hours: int
    product: str
    batches: tuple[BatchPlan, ...]
    quality_limits: ProcessLimits

    def to_dict(self) -> dict:
        return asdict(self)


def standard_campaign() -> CampaignDefinition:
    batches = tuple(
        BatchPlan(
            batch_id=f"BATCH-{i:02d}",
            planned_start_hour=(i - 1) * 54,
            material_lot_id=f"RM-{((i - 1) // 2) + 1:03d}",
        )
        for i in range(1, 13)
    )
    return CampaignDefinition("MAB-30D-001", 30 * 24, "MAB-DEMO", batches, ProcessLimits())
