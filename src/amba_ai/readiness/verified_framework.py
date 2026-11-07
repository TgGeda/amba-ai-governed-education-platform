from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


_METRIC_ID_RE = re.compile(r"^d(?P<dimension>[1-9]|1[0-3])_m(?P<metric>\d{2})$")
_EXPECTED_METRIC_COUNT = 111


class ReadinessFrameworkError(ValueError):
    pass


class ReadinessStatus(str, Enum):
    DEMONSTRATED = "demonstrated"
    PARTIALLY_DEMONSTRATED = "partially_demonstrated"
    NOT_DEMONSTRATED = "not_demonstrated"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNRESOLVED = "unresolved"


class ScoreStatus(str, Enum):
    WITHHELD_PENDING_METHODOLOGY_AND_EVIDENCE_COVERAGE = (
        "withheld_pending_methodology_and_evidence_coverage"
    )


class AssessmentSubjectType(str, Enum):
    PROJECT = "project"


class AssessmentMethod(str, Enum):
    PROJECT_LEVEL_SELF_EVALUATION = "project_level_self_evaluation"


@dataclass(frozen=True, slots=True)
class MaturityLevel:
    value: int
    label: str
    provenance: str = "reference_implementation"

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("value must be an integer")
        if not 0 <= self.value <= 5:
            raise ReadinessFrameworkError("maturity value must be between 0 and 5")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ReadinessFrameworkError("label must be a non-empty string")
        if self.provenance != "reference_implementation":
            raise ReadinessFrameworkError(
                "maturity labels must retain reference_implementation provenance"
            )


@dataclass(frozen=True, slots=True)
class ReferenceMetric:
    metric_id: str
    dimension_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.metric_id, str):
            raise TypeError("metric_id must be a string")
        match = _METRIC_ID_RE.fullmatch(self.metric_id)
        if match is None:
            raise ReadinessFrameworkError(f"invalid reference metric ID: {self.metric_id}")
        dimension = int(match.group("dimension"))
        if self.dimension_number != dimension:
            raise ReadinessFrameworkError(
                "dimension_number must match the dimension encoded in metric_id"
            )


@dataclass(frozen=True, slots=True)
class ReferenceMetricCatalog:
    source_path: str
    metrics: tuple[ReferenceMetric, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_path, str) or not self.source_path.strip():
            raise ReadinessFrameworkError("source_path must be a non-empty string")
        if Path(self.source_path).is_absolute():
            raise ReadinessFrameworkError("source_path must be repository-relative")
        if not isinstance(self.metrics, tuple):
            raise TypeError("metrics must be a tuple")
        ids = tuple(metric.metric_id for metric in self.metrics)
        if len(ids) != _EXPECTED_METRIC_COUNT:
            raise ReadinessFrameworkError(
                f"reference metric catalog must contain exactly {_EXPECTED_METRIC_COUNT} metrics"
            )
        if len(ids) != len(set(ids)):
            raise ReadinessFrameworkError("reference metric IDs must be unique")
        if "d1_m01" not in ids or "d13_m09" not in ids:
            raise ReadinessFrameworkError(
                "reference metric catalog must preserve d1_m01 and d13_m09"
            )
        if {metric.dimension_number for metric in self.metrics} != set(range(1, 14)):
            raise ReadinessFrameworkError("reference metrics must cover all 13 dimensions")

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(metric.metric_id for metric in self.metrics)

    @property
    def by_dimension(self) -> Mapping[int, tuple[ReferenceMetric, ...]]:
        grouped = {
            number: tuple(
                metric for metric in self.metrics if metric.dimension_number == number
            )
            for number in range(1, 14)
        }
        return MappingProxyType(grouped)


@dataclass(frozen=True, slots=True)
class VerifiedITUAIReadinessFramework:
    framework_id: str
    official_title: str
    report_version: str
    publication_date: str
    publisher: str
    electronic_isbn: str
    information_current_to: str
    factors: tuple[str, ...]
    dimensions: tuple[str, ...]
    dimension_to_factor_relationship: str
    metric_catalog: ReferenceMetricCatalog
    maturity_levels: tuple[MaturityLevel, ...]
    assessment_subject_type: AssessmentSubjectType
    assessment_subject_id: str
    jurisdictional_context: str
    national_assessment: bool
    official_itu_certification: bool
    assessment_method: AssessmentMethod
    permitted_statuses: tuple[ReadinessStatus, ...]
    overall_project_score: None
    score_status: ScoreStatus
    legal_determination_scope: bool
    metric_weighting_status: str
    factor_weighting_status: str
    dimension_weighting_status: str

    def __post_init__(self) -> None:
        if self.framework_id != "ITU-AI-READINESS-2.0":
            raise ReadinessFrameworkError("unexpected framework_id")
        if len(self.factors) != 6 or len(set(self.factors)) != 6:
            raise ReadinessFrameworkError("framework must contain exactly 6 unique factors")
        if len(self.dimensions) != 13 or len(set(self.dimensions)) != 13:
            raise ReadinessFrameworkError("framework must contain exactly 13 unique dimensions")
        if self.dimension_to_factor_relationship != "many_to_many":
            raise ReadinessFrameworkError("dimension-to-factor relationship must be many_to_many")
        if tuple(level.value for level in self.maturity_levels) != tuple(range(6)):
            raise ReadinessFrameworkError("maturity levels must preserve values 0 through 5")
        if self.assessment_subject_type is not AssessmentSubjectType.PROJECT:
            raise ReadinessFrameworkError("assessment subject must be project")
        if self.assessment_subject_id != "AMBA-GOV":
            raise ReadinessFrameworkError("assessment subject ID must be AMBA-GOV")
        if self.jurisdictional_context != "Ethiopia":
            raise ReadinessFrameworkError("jurisdictional context must be Ethiopia")
        if self.national_assessment is not False:
            raise ReadinessFrameworkError("national_assessment must be false")
        if self.official_itu_certification is not False:
            raise ReadinessFrameworkError("official_itu_certification must be false")
        if self.overall_project_score is not None:
            raise ReadinessFrameworkError("overall_project_score must remain null")
        if self.legal_determination_scope is not False:
            raise ReadinessFrameworkError("legal_determination_scope must be false")
        if set(self.permitted_statuses) != set(ReadinessStatus):
            raise ReadinessFrameworkError("permitted readiness statuses are incomplete")
        for status in (
            self.metric_weighting_status,
            self.factor_weighting_status,
            self.dimension_weighting_status,
        ):
            if status != "methodology_unresolved":
                raise ReadinessFrameworkError("all weighting statuses must remain methodology_unresolved")

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "official_title": self.official_title,
            "report_version": self.report_version,
            "publication_date": self.publication_date,
            "publisher": self.publisher,
            "electronic_isbn": self.electronic_isbn,
            "information_current_to": self.information_current_to,
            "factor_count": len(self.factors),
            "factors": list(self.factors),
            "dimension_count": len(self.dimensions),
            "dimensions": list(self.dimensions),
            "dimension_to_factor_relationship": self.dimension_to_factor_relationship,
            "metric_count": len(self.metric_catalog.metrics),
            "metric_ids": list(self.metric_catalog.metric_ids),
            "metric_catalog_source": self.metric_catalog.source_path,
            "maturity_levels": [
                {
                    "value": level.value,
                    "label": level.label,
                    "provenance": level.provenance,
                }
                for level in self.maturity_levels
            ],
            "assessment_scope": {
                "assessment_subject_type": self.assessment_subject_type.value,
                "assessment_subject_id": self.assessment_subject_id,
                "jurisdictional_context": self.jurisdictional_context,
                "national_assessment": self.national_assessment,
                "official_itu_certification": self.official_itu_certification,
                "assessment_method": self.assessment_method.value,
                "legal_determination_scope": self.legal_determination_scope,
            },
            "permitted_statuses": [status.value for status in self.permitted_statuses],
            "overall_project_score": self.overall_project_score,
            "score_status": self.score_status.value,
            "weighting_status": {
                "metric": self.metric_weighting_status,
                "factor": self.factor_weighting_status,
                "dimension": self.dimension_weighting_status,
            },
        }


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def load_reference_metric_catalog(
    path: Path | str,
    *,
    repository_root: Path | str | None = None,
) -> ReferenceMetricCatalog:
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"reference metric catalog not found: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReadinessFrameworkError("reference metric catalog is unreadable") from error
    metric_ids = sorted(
        {value for value in _walk_strings(payload) if _METRIC_ID_RE.fullmatch(value)},
        key=lambda metric_id: (
            int(_METRIC_ID_RE.fullmatch(metric_id).group("dimension")),
            int(_METRIC_ID_RE.fullmatch(metric_id).group("metric")),
        ),
    )
    metrics = tuple(
        ReferenceMetric(
            metric_id=metric_id,
            dimension_number=int(_METRIC_ID_RE.fullmatch(metric_id).group("dimension")),
        )
        for metric_id in metric_ids
    )
    if repository_root is None:
        rendered_path = source_path.as_posix()
        if source_path.is_absolute():
            rendered_path = source_path.name
    else:
        root = Path(repository_root).resolve()
        try:
            rendered_path = source_path.resolve().relative_to(root).as_posix()
        except ValueError as error:
            raise ReadinessFrameworkError("metric catalog must be inside repository_root") from error
    return ReferenceMetricCatalog(source_path=rendered_path, metrics=metrics)


def verified_itu_ai_readiness_framework(
    metric_catalog_path: Path | str,
    *,
    repository_root: Path | str | None = None,
) -> VerifiedITUAIReadinessFramework:
    catalog = load_reference_metric_catalog(
        metric_catalog_path,
        repository_root=repository_root,
    )
    return VerifiedITUAIReadinessFramework(
        framework_id="ITU-AI-READINESS-2.0",
        official_title="AI Ready – Analysis Towards a Standardized Readiness Framework",
        report_version="2.0",
        publication_date="January 2026",
        publisher="International Telecommunication Union",
        electronic_isbn="978-92-61-41911-0",
        information_current_to="June 2025",
        factors=(
            "Data",
            "Research",
            "Deployment Support",
            "Standards",
            "Open Source and Code",
            "Sandbox Environments",
        ),
        dimensions=(
            "Data/model Marketplace",
            "Generated Content Marketplace",
            "Cross-domain Correlation Analysis",
            "Contextualization and Regional Impact",
            "Level of Integration of AI in Workflows",
            "Human Interface",
            "Strategy Alignment",
            "Collaboration with AI",
            "Impacts of Humans in AI Integration",
            "AI & Policies",
            "AI for Inclusion",
            "Granular Priorities",
            "Digital Infrastructure",
        ),
        dimension_to_factor_relationship="many_to_many",
        metric_catalog=catalog,
        maturity_levels=(
            MaturityLevel(0, "Not Started"),
            MaturityLevel(1, "Initial / Ad-hoc"),
            MaturityLevel(2, "Developing"),
            MaturityLevel(3, "Established"),
            MaturityLevel(4, "Advanced"),
            MaturityLevel(5, "Leading / Optimizing"),
        ),
        assessment_subject_type=AssessmentSubjectType.PROJECT,
        assessment_subject_id="AMBA-GOV",
        jurisdictional_context="Ethiopia",
        national_assessment=False,
        official_itu_certification=False,
        assessment_method=AssessmentMethod.PROJECT_LEVEL_SELF_EVALUATION,
        permitted_statuses=tuple(ReadinessStatus),
        overall_project_score=None,
        score_status=ScoreStatus.WITHHELD_PENDING_METHODOLOGY_AND_EVIDENCE_COVERAGE,
        legal_determination_scope=False,
        metric_weighting_status="methodology_unresolved",
        factor_weighting_status="methodology_unresolved",
        dimension_weighting_status="methodology_unresolved",
    )
