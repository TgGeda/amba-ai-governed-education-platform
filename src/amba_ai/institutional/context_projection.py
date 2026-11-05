from __future__ import annotations

import threading

from amba_ai.governance.models import IdentifierProvider
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.clock import ScenarioClockProtocol
from amba_ai.scenarios.models import (
    EvidenceReleaseEnvelope,
    ScenarioConfigurationError,
    require_identifier,
    sha256_canonical,
)


class InstitutionalContextProjectionService:
    def __init__(
        self,
        *,
        identifier_provider: IdentifierProvider,
        clock: ScenarioClockProtocol,
    ) -> None:
        if not callable(getattr(identifier_provider, "new_id", None)):
            raise TypeError("identifier_provider must provide new_id")
        if not isinstance(clock, ScenarioClockProtocol):
            raise TypeError("clock must implement ScenarioClockProtocol")
        self._identifier_provider = identifier_provider
        self._clock = clock
        self._projections: dict[str, InstitutionalContextProjection] = {}
        self._projection_ids: set[str] = set()
        self._lock = threading.RLock()

    @property
    def clock(self) -> ScenarioClockProtocol:
        return self._clock

    def project(
        self,
        envelope: EvidenceReleaseEnvelope,
    ) -> InstitutionalContextProjection:
        if not isinstance(envelope, EvidenceReleaseEnvelope):
            raise TypeError("envelope must be an EvidenceReleaseEnvelope")
        if envelope.compute_digest() != envelope.release_digest:
            raise ScenarioConfigurationError(
                "source release digest does not match release contents"
            )
        with self._lock:
            existing = self._projections.get(envelope.release_digest)
            if existing is not None:
                self._validate_exact_projection(existing, envelope)
                return existing
            snapshot = self._clock.snapshot()
            if envelope.stage > snapshot.stage:
                raise ScenarioConfigurationError(
                    "source release stage exceeds the projection clock stage"
                )
            projection_id = require_identifier(
                self._identifier_provider.new_id("projection"),
                "generated projection_id",
            )
            if projection_id in self._projection_ids:
                raise ScenarioConfigurationError(
                    "identifier provider returned a duplicate projection_id"
                )
            metadata = {
                "source_release_verified": True,
                "recipient_scope_preserved": True,
                "fact_set_preserved": True,
                "governance_decision_created": False,
                "approval_created": False,
                "execution_requested": False,
                "distribution_attempted": False,
            }
            payload = {
                "projection_id": projection_id,
                "scenario_id": envelope.scenario_id,
                "stage": int(envelope.stage),
                "recipient_id": envelope.recipient_id,
                "source_release_id": envelope.release_id,
                "source_release_digest": envelope.release_digest,
                "projected_at": snapshot.timestamp,
                "facts": [fact.to_dict() for fact in envelope.facts],
                "metadata": metadata,
                "synthetic": True,
                "legal_effect": False,
            }
            projection = InstitutionalContextProjection(
                projection_id=projection_id,
                scenario_id=envelope.scenario_id,
                stage=envelope.stage,
                recipient_id=envelope.recipient_id,
                source_release_id=envelope.release_id,
                source_release_digest=envelope.release_digest,
                projected_at=snapshot.timestamp,
                facts=envelope.facts,
                metadata=metadata,
                projection_digest=sha256_canonical(payload),
            )
            self._validate_exact_projection(projection, envelope)
            self._projections[envelope.release_digest] = projection
            self._projection_ids.add(projection_id)
            return projection

    def get_by_release_digest(
        self,
        release_digest: str,
    ) -> InstitutionalContextProjection | None:
        normalized = release_digest.strip().lower() if isinstance(release_digest, str) else ""
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef"
            for character in normalized
        ):
            raise ScenarioConfigurationError(
                "release_digest must be a SHA-256 digest"
            )
        with self._lock:
            return self._projections.get(normalized)

    @staticmethod
    def _validate_exact_projection(
        projection: InstitutionalContextProjection,
        envelope: EvidenceReleaseEnvelope,
    ) -> None:
        if projection.scenario_id != envelope.scenario_id:
            raise ScenarioConfigurationError(
                "projection scenario does not match source release"
            )
        if projection.stage is not envelope.stage:
            raise ScenarioConfigurationError(
                "projection stage does not match source release"
            )
        if projection.recipient_id != envelope.recipient_id:
            raise ScenarioConfigurationError(
                "projection recipient does not match source release"
            )
        if projection.source_release_id != envelope.release_id:
            raise ScenarioConfigurationError(
                "projection release identifier does not match source release"
            )
        if projection.source_release_digest != envelope.release_digest:
            raise ScenarioConfigurationError(
                "projection digest reference does not match source release"
            )
        if projection.fact_ids != envelope.fact_ids:
            raise ScenarioConfigurationError(
                "projection fact set does not exactly match source release"
            )
        if projection.fact_digests != tuple(
            fact.fact_digest for fact in envelope.facts
        ):
            raise ScenarioConfigurationError(
                "projection fact contents do not exactly match source release"
            )
