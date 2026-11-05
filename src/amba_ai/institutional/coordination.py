from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import threading
from typing import Any

from amba_ai.governance.models import (
    IdentifierProvider,
    deep_freeze,
    to_canonical_json,
)
from amba_ai.institutional.assessment import (
    InstitutionalAssessment,
)
from amba_ai.institutional.conflict_resolution import (
    InstitutionalConflict,
    InstitutionalConflictDetector,
    SourcedQuestion,
)
from amba_ai.institutional.models import (
    InstitutionalContextProjection,
)
from amba_ai.institutional.registry import (
    InstitutionalAssessorRegistry,
)
from amba_ai.scenarios.clock import (
    ScenarioClockProtocol,
)
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    ScenarioStage,
    normalize_identifiers,
    require_identifier,
    require_sha256,
    require_timestamp,
    sha256_canonical,
)


@dataclass(frozen=True, slots=True)
class InstitutionalCoordinationResult:
    coordination_id: str
    scenario_id: str
    stage: ScenarioStage
    projection_ids: tuple[str, ...]
    assessments: tuple[InstitutionalAssessment, ...]
    conflicts: tuple[InstitutionalConflict, ...]
    unresolved_questions: tuple[SourcedQuestion, ...]
    uncovered_fact_ids: tuple[str, ...]
    coordinated_at: str
    metadata: Mapping[str, Any]
    coordination_digest: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "coordination_id",
            require_identifier(
                self.coordination_id,
                "coordination_id",
            ),
        )
        object.__setattr__(
            self,
            "scenario_id",
            require_identifier(
                self.scenario_id,
                "scenario_id",
            ),
        )
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError(
                "stage must be a ScenarioStage"
            )
        projection_ids = normalize_identifiers(
            self.projection_ids,
            "projection_ids",
        )
        if not projection_ids:
            raise ScenarioConfigurationError(
                "projection_ids must not be empty"
            )
        object.__setattr__(
            self,
            "projection_ids",
            projection_ids,
        )
        if not isinstance(self.assessments, tuple):
            raise TypeError(
                "assessments must be a tuple"
            )
        if any(
            not isinstance(
                item,
                InstitutionalAssessment,
            )
            for item in self.assessments
        ):
            raise TypeError(
                "assessments must contain "
                "InstitutionalAssessment objects"
            )
        canonical_assessments = tuple(
            sorted(
                self.assessments,
                key=lambda item: (
                    item.institution_id,
                    item.assessment_id,
                ),
            )
        )
        if canonical_assessments != self.assessments:
            raise ScenarioConfigurationError(
                "assessments must use deterministic order"
            )
        assessment_ids = tuple(
            item.assessment_id
            for item in self.assessments
        )
        if len(assessment_ids) != len(
            set(assessment_ids)
        ):
            raise ScenarioConfigurationError(
                "assessments must not contain duplicates"
            )
        for assessment in self.assessments:
            if assessment.scenario_id != self.scenario_id:
                raise ScenarioConfigurationError(
                    "assessment scenario does not match coordination"
                )
            if assessment.stage is not self.stage:
                raise ScenarioConfigurationError(
                    "assessment stage does not match coordination"
                )
            if assessment.projection_id not in projection_ids:
                raise ScenarioConfigurationError(
                    "assessment projection is not in coordination scope"
                )
        if not isinstance(self.conflicts, tuple):
            raise TypeError(
                "conflicts must be a tuple"
            )
        if any(
            not isinstance(item, InstitutionalConflict)
            for item in self.conflicts
        ):
            raise TypeError(
                "conflicts must contain InstitutionalConflict objects"
            )
        conflict_ids = tuple(
            item.conflict_id for item in self.conflicts
        )
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ScenarioConfigurationError(
                "conflicts must not contain duplicates"
            )
        valid_assessment_ids = set(assessment_ids)
        for conflict in self.conflicts:
            if not set(conflict.assessment_ids).issubset(
                valid_assessment_ids
            ):
                raise ScenarioConfigurationError(
                    "conflict references an assessment outside coordination"
                )
        if not isinstance(
            self.unresolved_questions,
            tuple,
        ):
            raise TypeError(
                "unresolved_questions must be a tuple"
            )
        if any(
            not isinstance(item, SourcedQuestion)
            for item in self.unresolved_questions
        ):
            raise TypeError(
                "unresolved_questions must contain SourcedQuestion objects"
            )
        question_keys = tuple(
            (
                item.institution_id,
                item.assessment_id,
                item.question,
            )
            for item in self.unresolved_questions
        )
        if len(question_keys) != len(set(question_keys)):
            raise ScenarioConfigurationError(
                "unresolved_questions must not contain duplicates"
            )
        object.__setattr__(
            self,
            "uncovered_fact_ids",
            normalize_identifiers(
                self.uncovered_fact_ids,
                "uncovered_fact_ids",
            ),
        )
        object.__setattr__(
            self,
            "coordinated_at",
            require_timestamp(
                self.coordinated_at,
                "coordinated_at",
            ),
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError(
                "metadata must be a mapping"
            )
        metadata = deep_freeze(self.metadata)
        prohibited = {
            "recommended_action",
            "approval_decision",
            "authorization_result",
            "distribution_disposition",
            "consensus_status",
        }
        if prohibited.intersection(metadata):
            raise ScenarioConfigurationError(
                "coordination metadata must not contain decisions "
                "or manufactured consensus"
            )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(
            self,
            "coordination_digest",
            require_sha256(
                self.coordination_digest,
                "coordination_digest",
            ),
        )
        if type(self.synthetic) is not bool:
            raise TypeError(
                "synthetic must be a strict Boolean"
            )
        if type(self.legal_effect) is not bool:
            raise TypeError(
                "legal_effect must be a strict Boolean"
            )
        if not self.synthetic or self.legal_effect:
            raise ScenarioConfigurationError(
                "coordination must remain synthetic "
                "and without legal effect"
            )
        if self.coordination_digest != self.compute_digest():
            raise ScenarioConfigurationError(
                "coordination_digest does not match contents"
            )
        to_canonical_json(self.to_dict())

    def digest_payload(self) -> dict[str, Any]:
        return {
            "coordination_id": self.coordination_id,
            "scenario_id": self.scenario_id,
            "stage": int(self.stage),
            "projection_ids": list(
                self.projection_ids
            ),
            "assessments": [
                item.to_dict()
                for item in self.assessments
            ],
            "conflicts": [
                item.to_dict()
                for item in self.conflicts
            ],
            "unresolved_questions": [
                item.to_dict()
                for item in self.unresolved_questions
            ],
            "uncovered_fact_ids": list(
                self.uncovered_fact_ids
            ),
            "coordinated_at": self.coordinated_at,
            "metadata": self.metadata,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(
            self.digest_payload()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.digest_payload(),
            "coordination_digest": (
                self.coordination_digest
            ),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class InstitutionalCoordinationService:
    def __init__(
        self,
        *,
        registry: InstitutionalAssessorRegistry,
        conflict_detector: InstitutionalConflictDetector,
        identifier_provider: IdentifierProvider,
        clock: ScenarioClockProtocol,
    ) -> None:
        if not isinstance(
            registry,
            InstitutionalAssessorRegistry,
        ):
            raise TypeError(
                "registry must be an InstitutionalAssessorRegistry"
            )
        if not isinstance(
            conflict_detector,
            InstitutionalConflictDetector,
        ):
            raise TypeError(
                "conflict_detector must be an InstitutionalConflictDetector"
            )
        if not callable(
            getattr(identifier_provider, "new_id", None)
        ):
            raise TypeError(
                "identifier_provider must provide new_id"
            )
        if not isinstance(clock, ScenarioClockProtocol):
            raise TypeError(
                "clock must implement ScenarioClockProtocol"
            )
        self._registry = registry
        self._conflict_detector = conflict_detector
        self._identifier_provider = identifier_provider
        self._clock = clock
        self._results: dict[
            str,
            InstitutionalCoordinationResult,
        ] = {}
        self._lock = threading.RLock()

    def coordinate(
        self,
        projections: tuple[
            InstitutionalContextProjection,
            ...,
        ],
    ) -> InstitutionalCoordinationResult:
        if not isinstance(projections, tuple):
            raise TypeError(
                "projections must be a tuple"
            )
        if not projections:
            raise ScenarioConfigurationError(
                "projections must not be empty"
            )
        if any(
            not isinstance(
                item,
                InstitutionalContextProjection,
            )
            for item in projections
        ):
            raise TypeError(
                "projections must contain "
                "InstitutionalContextProjection objects"
            )
        projection_ids = tuple(
            item.projection_id for item in projections
        )
        if len(projection_ids) != len(set(projection_ids)):
            raise ScenarioConfigurationError(
                "projections must not contain duplicate identifiers"
            )
        recipients = tuple(
            item.recipient_id for item in projections
        )
        if len(recipients) != len(set(recipients)):
            raise ScenarioConfigurationError(
                "only one projection per recipient may be coordinated"
            )
        scenario_ids = {
            item.scenario_id for item in projections
        }
        stages = {item.stage for item in projections}
        if len(scenario_ids) != 1:
            raise ScenarioConfigurationError(
                "all projections must share one scenario_id"
            )
        if len(stages) != 1:
            raise ScenarioConfigurationError(
                "all projections must share one scenario stage"
            )
        ordered = tuple(
            sorted(
                projections,
                key=lambda item: (
                    item.recipient_id,
                    item.projection_id,
                ),
            )
        )
        scope_key = sha256_canonical(
            {
                "projection_digests": [
                    item.projection_digest
                    for item in ordered
                ]
            }
        )
        with self._lock:
            existing = self._results.get(scope_key)
            if existing is not None:
                return existing
            assessments = tuple(
                sorted(
                    (
                        self._registry
                        .get_by_recipient(
                            projection.recipient_id
                        )
                        .assess(projection)
                        for projection in ordered
                    ),
                    key=lambda item: (
                        item.institution_id,
                        item.assessment_id,
                    ),
                )
            )
            conflicts = self._conflict_detector.detect(
                assessments
            )
            questions = tuple(
                SourcedQuestion(
                    institution_id=(
                        assessment.institution_id
                    ),
                    mandate_id=assessment.mandate_id,
                    assessment_id=(
                        assessment.assessment_id
                    ),
                    question=question,
                )
                for assessment in assessments
                for question in (
                    assessment.unresolved_questions
                )
            )
            projected_fact_ids = {
                fact_id
                for projection in ordered
                for fact_id in projection.fact_ids
            }
            assessed_fact_ids = {
                fact_id
                for assessment in assessments
                for fact_id in (
                    assessment.assessed_fact_ids
                )
            }
            uncovered = tuple(
                sorted(
                    projected_fact_ids
                    - assessed_fact_ids
                )
            )
            snapshot = self._clock.snapshot()
            stage = ordered[0].stage
            if stage > snapshot.stage:
                raise ScenarioConfigurationError(
                    "coordination stage exceeds clock stage"
                )
            coordination_id = require_identifier(
                self._identifier_provider.new_id(
                    "coordination"
                ),
                "generated coordination_id",
            )
            metadata = {
                "all_assessments_preserved": True,
                "conflicts_preserved": True,
                "consensus_manufactured": False,
                "governance_recommendation_created": False,
                "approval_created": False,
                "execution_requested": False,
                "distribution_attempted": False,
            }
            payload = {
                "coordination_id": coordination_id,
                "scenario_id": ordered[0].scenario_id,
                "stage": int(stage),
                "projection_ids": [
                    item.projection_id
                    for item in ordered
                ],
                "assessments": [
                    item.to_dict()
                    for item in assessments
                ],
                "conflicts": [
                    item.to_dict()
                    for item in conflicts
                ],
                "unresolved_questions": [
                    item.to_dict()
                    for item in questions
                ],
                "uncovered_fact_ids": list(uncovered),
                "coordinated_at": snapshot.timestamp,
                "metadata": metadata,
                "synthetic": True,
                "legal_effect": False,
            }
            result = InstitutionalCoordinationResult(
                coordination_id=coordination_id,
                scenario_id=ordered[0].scenario_id,
                stage=stage,
                projection_ids=tuple(
                    item.projection_id
                    for item in ordered
                ),
                assessments=assessments,
                conflicts=conflicts,
                unresolved_questions=questions,
                uncovered_fact_ids=uncovered,
                coordinated_at=snapshot.timestamp,
                metadata=metadata,
                coordination_digest=sha256_canonical(
                    payload
                ),
            )
            self._results[scope_key] = result
            return result
