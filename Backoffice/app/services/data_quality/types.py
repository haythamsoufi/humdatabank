"""Types for data quality scoring results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataQualityResult:
    overall_pct: float
    methodology: str
    template_id: int
    entity_type: str
    entity_id: int
    period_name: str
    pillars: dict[str, Any] = field(default_factory=dict)
    sub_pillars: dict[str, Any] = field(default_factory=dict)
    trend: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_pct": round(self.overall_pct, 1),
            "methodology": self.methodology,
            "template_id": self.template_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "period_name": self.period_name,
            "pillars": self.pillars,
            "sub_pillars": self.sub_pillars,
            "trend": self.trend,
            "warnings": self.warnings,
            "validation_summary": self.validation_summary,
        }
