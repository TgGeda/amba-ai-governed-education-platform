from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    finding_id: str
    element_type: str
    element_id: str
    name: str
    weight: float

@dataclass(frozen=True, slots=True)
class MetricEvaluation:
    metric_id: str
    finding_id: str
    element_type: str
    element_id: str
    status: str
    weight: float
    applicable: bool
    scored: bool
    score: float | None
    evidence_pointers: tuple[str, ...]
    rationale: str
    def to_dict(self) -> dict[str, Any]:
        return {"metric_id": self.metric_id, "finding_id": self.finding_id, "element_type": self.element_type, "element_id": self.element_id, "status": self.status, "weight": self.weight, "applicable": self.applicable, "scored": self.scored, "score": self.score, "evidence_pointers": list(self.evidence_pointers), "rationale": self.rationale}

@dataclass(frozen=True, slots=True)
class CoverageResult:
    total_metric_count: int
    applicable_metric_count: int
    scored_metric_count: int
    excluded_metric_count: int
    unscored_metric_count: int
    applicable_weight: float
    scored_weight: float
    coverage_ratio: float
    minimum_required_ratio: float
    sufficient: bool
    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float | None
    status: str
    coverage: CoverageResult
    weighted_score_sum: float
    scored_weight: float
    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "status": self.status, "coverage": self.coverage.to_dict(), "weighted_score_sum": self.weighted_score_sum, "scored_weight": self.scored_weight}
