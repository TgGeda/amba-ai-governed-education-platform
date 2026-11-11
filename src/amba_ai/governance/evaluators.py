from __future__ import annotations

import math
from typing import Any, Mapping, Protocol, runtime_checkable

from amba_ai.governance.models import (
    AuthorizationBasis,
    BindingLevel,
    ContentSafetyResult,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    GovernanceConfigurationError,
    IdentifierProvider,
    PipelineEvent,
    PolicyFinding,
    PolicyRecordAmbiguityError,
    PolicyRecordIdentity,
    PolicyVerdict,
    ResolvedOperation,
)
from amba_ai.governance.operation_registry import DestinationRegistry
from amba_ai.governance.record_registry import PolicyRecordRegistry


RESTRICTED_DESTINATIONS_RECORD_ID = (
    "PROJECT-CONTROL-RESTRICTED-DESTINATIONS-V1"
)
EDUCATIONAL_PROCESSING_RECORD_ID = (
    "PROJECT-CONTROL-EDUCATIONAL-PROCESSING-V1"
)
COMMERCIAL_PURCHASES_RECORD_ID = (
    "PROJECT-CONTROL-COMMERCIAL-PURCHASES-V1"
)
TARGETED_ADVERTISING_RECORD_ID = (
    "PROJECT-CONTROL-TARGETED-ADVERTISING-V1"
)
EXACT_PROHIBITED_INFERENCE_SIGNAL = (
    "simulated_prohibited_inference_signal_v1"
)


def _require_dependency(value: Any, field_name: str) -> None:
    if value is None:
        raise GovernanceConfigurationError(
            f"{field_name} is required"
        )


def _validate_evaluation_inputs(
    event: PipelineEvent,
    operation: ResolvedOperation,
    record_registry: PolicyRecordRegistry,
) -> None:
    if not isinstance(event, PipelineEvent):
        raise TypeError("event must be a PipelineEvent")
    if not isinstance(operation, ResolvedOperation):
        raise TypeError("operation must be a ResolvedOperation")
    if not isinstance(record_registry, PolicyRecordRegistry):
        raise TypeError(
            "record_registry must be a PolicyRecordRegistry"
        )
    if event.operation_id != operation.operation_id:
        raise GovernanceConfigurationError(
            "Event operation does not match resolved operation"
        )


def _finding(
    *,
    finding_id: str,
    event: PipelineEvent,
    evaluator_id: str,
    code: str,
    severity: FindingSeverity,
    verdict: PolicyVerdict,
    rationale: str,
    sufficiency: EvidenceSufficiency,
    primary_records: tuple[PolicyRecordIdentity, ...] = (),
    details: Mapping[str, Any] | None = None,
) -> PolicyFinding:
    return PolicyFinding(
        finding_id=finding_id,
        event_id=event.event_id,
        finding_code=code,
        basis_category=BindingLevel.PROJECT_CONTROL,
        severity=severity,
        verdict=verdict,
        evaluator_id=evaluator_id,
        primary_records=primary_records,
        supporting_records=(),
        rationale=rationale,
        evidence_sufficiency=sufficiency,
        deterministic_result=True,
        applicability_details=dict(details or {}),
    )


def _active_enforcement_record(
    registry: PolicyRecordRegistry,
    record_id: str,
):
    record = registry.get_active_by_record_id(record_id)
    if (
        record is None
        or not registry.eligible_for_project_enforcement(record.identity)
    ):
        return None
    return record


@runtime_checkable
class ContentSafetyChecker(Protocol):
    def check_content(
        self,
        payload: Mapping[str, Any],
    ) -> ContentSafetyResult | None:
        ...


class _BaseEvaluator:
    evaluator_id: str
    evaluator_version = "1.0.0"

    def __init__(self, id_provider: IdentifierProvider) -> None:
        _require_dependency(id_provider, "id_provider")
        if not callable(getattr(id_provider, "new_id", None)):
            raise TypeError(
                "id_provider must satisfy IdentifierProvider"
            )
        self._ids = id_provider

    def _begin(
        self,
        prefix: str,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> str:
        _validate_evaluation_inputs(
            event,
            operation,
            record_registry,
        )
        return self._ids.new_id(prefix)


class AuthorizationBasisEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-AUTHORIZATION-BASIS"

    def evaluate(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> PolicyFinding:
        fid = self._begin(
            "find_auth", event, operation, record_registry
        )
        if not operation.authorization_basis_required:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="AUTH_NOT_REQUIRED",
                severity=FindingSeverity.INFO,
                verdict=PolicyVerdict.NOT_APPLICABLE,
                rationale=(
                    "The operation does not require a formal "
                    "authorization basis."
                ),
                sufficiency=EvidenceSufficiency.NOT_APPLICABLE,
                details={"operation_id": operation.operation_id},
            )

        authorization = event.authorization_basis
        if authorization is None:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="AUTH_BASIS_MISSING",
                severity=FindingSeverity.RESTRICTIVE,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale=(
                    "The operation requires an active authorization "
                    "basis, but none was supplied."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"has_auth_basis": False},
            )

        basis_type = authorization.basis_type.value
        if basis_type not in operation.allowed_authorization_basis_types:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="AUTH_BASIS_TYPE_NOT_ALLOWED",
                severity=FindingSeverity.RESTRICTIVE,
                verdict=PolicyVerdict.NONCOMPLIANT,
                rationale=(
                    "The authorization-basis type is not permitted "
                    "for the resolved operation."
                ),
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                details={"basis_type": basis_type},
            )

        raw_purpose = event.payload.get(
            "purpose", operation.operation_id
        )
        if not isinstance(raw_purpose, str) or not raw_purpose.strip():
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="AUTH_PURPOSE_INVALID",
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale=(
                    "The event purpose must be a nonempty string."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"purpose_valid": False},
            )

        valid = authorization.is_valid(
            purpose=raw_purpose.strip(),
            operation=operation.operation_id,
            now_iso=event.timestamp,
        )
        return _finding(
            finding_id=fid,
            event=event,
            evaluator_id=self.evaluator_id,
            code=(
                "AUTH_BASIS_VALID"
                if valid
                else "AUTH_BASIS_INVALID_OR_EXPIRED"
            ),
            severity=(
                FindingSeverity.INFO
                if valid
                else FindingSeverity.RESTRICTIVE
            ),
            verdict=(
                PolicyVerdict.COMPLIANT
                if valid
                else PolicyVerdict.NONCOMPLIANT
            ),
            rationale=(
                "The authorization basis was validated within "
                "project scope."
                if valid
                else "The authorization basis failed purpose, "
                "operation, or temporal validation."
            ),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            details={
                "valid": valid,
                "basis_id": authorization.basis_id,
            },
        )


class DestinationEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-DESTINATION"

    def __init__(
        self,
        id_provider: IdentifierProvider,
        destination_registry: DestinationRegistry,
    ) -> None:
        super().__init__(id_provider)
        _require_dependency(
            destination_registry,
            "destination_registry",
        )
        if not isinstance(destination_registry, DestinationRegistry):
            raise TypeError(
                "destination_registry must be a DestinationRegistry"
            )
        self._destinations = destination_registry

    def evaluate(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> PolicyFinding:
        fid = self._begin(
            "find_dest", event, operation, record_registry
        )
        try:
            record = _active_enforcement_record(
                record_registry,
                RESTRICTED_DESTINATIONS_RECORD_ID,
            )
        except PolicyRecordAmbiguityError:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="DEST_RECORD_AMBIGUOUS",
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale=(
                    "The restricted-destinations control has multiple "
                    "active versions."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"record_id": RESTRICTED_DESTINATIONS_RECORD_ID},
            )

        if record is None:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="DEST_RECORD_INACTIVE",
                severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale=(
                    "The restricted-destinations control is missing "
                    "or inactive."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"missing_record": RESTRICTED_DESTINATIONS_RECORD_ID},
            )

        destination_id = event.destination_id
        specification = self._destinations.get(destination_id)
        records = (record.identity,)

        if specification is None:
            configuration_failure = (
                self._destinations.rules.unknown_destination
                == FailureBehavior.CONFIGURATION_FAILURE
            )
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="DESTINATION_UNKNOWN",
                severity=FindingSeverity.CRITICAL,
                verdict=(
                    PolicyVerdict.CONFIGURATION_FAILURE
                    if configuration_failure
                    else PolicyVerdict.NONCOMPLIANT
                ),
                rationale=(
                    "The destination is not present in destination "
                    "configuration."
                ),
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                primary_records=records,
                details={"destination_id": destination_id, "known": False},
            )

        if not specification.registered:
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="DESTINATION_UNREGISTERED",
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.NONCOMPLIANT,
                rationale=(
                    "The destination is not registered for active "
                    "delivery."
                ),
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                primary_records=records,
                details={"destination_id": destination_id, "registered": False},
            )

        if not self._destinations.is_allowed_for_operation(
            destination_id,
            operation.operation_id,
        ):
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="DESTINATION_OPERATION_INELIGIBLE",
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.NONCOMPLIANT,
                rationale=(
                    "The destination is not authorized for the "
                    "resolved operation."
                ),
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                primary_records=records,
                details={
                    "destination_id": destination_id,
                    "operation_id": operation.operation_id,
                },
            )

        return _finding(
            finding_id=fid,
            event=event,
            evaluator_id=self.evaluator_id,
            code="DESTINATION_APPROVED",
            severity=FindingSeverity.INFO,
            verdict=PolicyVerdict.COMPLIANT,
            rationale=(
                "The destination conforms to sandbox routing rules."
            ),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            primary_records=records,
            details={"destination_id": destination_id},
        )


class _RecordBackedEvaluator(_BaseEvaluator):
    record_id: str
    ambiguous_code: str
    inactive_code: str
    prefix: str

    def _load_record(
        self,
        fid: str,
        event: PipelineEvent,
        registry: PolicyRecordRegistry,
    ):
        try:
            record = _active_enforcement_record(
                registry,
                self.record_id,
            )
        except PolicyRecordAmbiguityError:
            return None, _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code=self.ambiguous_code,
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale=(
                    "The required control has multiple active versions."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"record_id": self.record_id},
            )

        if record is None:
            return None, _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code=self.inactive_code,
                severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale=(
                    "The required project control is missing or inactive."
                ),
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"missing_record": self.record_id},
            )
        return record, None


class ProjectEducationalProcessingEvaluator(_RecordBackedEvaluator):
    evaluator_id = "EVAL-PROJECT-EDUCATIONAL-PROCESSING"
    record_id = EDUCATIONAL_PROCESSING_RECORD_ID
    ambiguous_code = "EDU_RECORD_AMBIGUOUS"
    inactive_code = "EDU_RECORD_INACTIVE"

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_edu", event, operation, record_registry)
        record, failure = self._load_record(fid, event, record_registry)
        if failure is not None:
            return failure
        commercial = event.payload.get("commercial_sdk_active", False)
        if type(commercial) is not bool:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="COMMERCIAL_SDK_FLAG_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="commercial_sdk_active must be a strict Boolean.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                primary_records=(record.identity,), details={"valid": False},
            )
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("PROJECT_CONTROL_COMMERCIAL_DRIFT_HELD" if commercial else "EDU_PROCESSING_COMPLIANT"),
            severity=(FindingSeverity.RESTRICTIVE if commercial else FindingSeverity.INFO),
            verdict=(PolicyVerdict.NONCOMPLIANT if commercial else PolicyVerdict.COMPLIANT),
            rationale=(
                "Commercial SDK execution was detected in the educational stream."
                if commercial else
                "The event conforms to educational-processing controls."
            ),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            primary_records=(record.identity,),
            details={"commercial_sdk_active": commercial},
        )


class CitationIntegrityEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-CITATION-INTEGRITY"

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_cit", event, operation, record_registry)
        if event.payload.get("governance_phase") == "pre_generation":
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="CITATION_NOT_YET_AVAILABLE",
                severity=FindingSeverity.INFO,
                verdict=PolicyVerdict.NOT_APPLICABLE,
                rationale="Citation integrity is evaluated after governed generation.",
                sufficiency=EvidenceSufficiency.NOT_APPLICABLE,
                details={"governance_phase": "pre_generation"},
            )
        citations = event.payload.get("citations")
        if citations is None or citations == () or citations == []:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="CITATION_MISSING", severity=FindingSeverity.ADVISORY,
                verdict=PolicyVerdict.POTENTIAL_GAP,
                rationale="The output has no structured citations.",
                sufficiency=EvidenceSufficiency.PARTIAL,
                details={"citation_count": 0},
            )
        if not isinstance(citations, (list, tuple)):
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="CITATION_COLLECTION_INVALID", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="citations must be a list or tuple.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"collection_valid": False},
            )

        verified: list[PolicyRecordIdentity] = []
        unverified = False
        for item in citations:
            if not isinstance(item, Mapping):
                return _finding(
                    finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                    code="CITATION_ARBITRARY_STRING_REJECTED",
                    severity=FindingSeverity.WARNING,
                    verdict=PolicyVerdict.POTENTIAL_GAP,
                    rationale="Citations must be structured mappings.",
                    sufficiency=EvidenceSufficiency.INSUFFICIENT,
                    details={"invalid_item_type": type(item).__name__},
                )
            keys = set(item)
            if {"record_id", "version_id", "source_id"}.issubset(keys):
                try:
                    identity = PolicyRecordIdentity(
                        record_id=item["record_id"],
                        version_id=item["version_id"],
                        source_id=item["source_id"],
                    )
                except (TypeError, ValueError):
                    unverified = True
                    continue
                record = record_registry.get(identity)
                if record is not None and record_registry.eligible_for_citation(identity):
                    verified.append(identity)
                else:
                    unverified = True
            elif {"source_id", "locator"}.issubset(keys):
                source = item.get("source_id")
                locator = item.get("locator")
                if not isinstance(source, str) or not source.strip() or not isinstance(locator, str) or not locator.strip():
                    return _finding(
                        finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                        code="CITATION_STRUCTURE_INVALID", severity=FindingSeverity.WARNING,
                        verdict=PolicyVerdict.POTENTIAL_GAP,
                        rationale="Citation locator fields must be nonempty strings.",
                        sufficiency=EvidenceSufficiency.PARTIAL,
                        details={"structure_valid": False},
                    )
                unverified = True
            else:
                return _finding(
                    finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                    code="CITATION_STRUCTURE_INVALID", severity=FindingSeverity.WARNING,
                    verdict=PolicyVerdict.POTENTIAL_GAP,
                    rationale="Citation fields do not match a supported structure.",
                    sufficiency=EvidenceSufficiency.PARTIAL,
                    details={"rejected_keys": tuple(sorted(str(key) for key in keys))},
                )

        verified_unique = tuple(sorted(set(verified), key=str))
        if verified_unique and not unverified:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="CITATION_VERIFIED", severity=FindingSeverity.INFO,
                verdict=PolicyVerdict.COMPLIANT,
                rationale="All citations reference active verified policy records.",
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                primary_records=verified_unique,
                details={"verified_count": len(verified_unique)},
            )
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("CITATION_PARTIALLY_VERIFIED" if verified_unique else "CITATION_STRUCTURALLY_VALID_UNVERIFIED"),
            severity=FindingSeverity.ADVISORY,
            verdict=PolicyVerdict.POTENTIAL_GAP,
            rationale="One or more citations remain unverified.",
            sufficiency=EvidenceSufficiency.PARTIAL,
            primary_records=verified_unique,
            details={"verified_count": len(verified_unique), "has_unverified": True},
        )


class ContentSafetyEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-CONTENT-SAFETY"

    def __init__(
        self,
        id_provider: IdentifierProvider,
        checker: ContentSafetyChecker | None = None,
    ) -> None:
        super().__init__(id_provider)
        if checker is not None and not isinstance(checker, ContentSafetyChecker):
            raise TypeError("checker must satisfy ContentSafetyChecker")
        self._checker = checker

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_safety", event, operation, record_registry)
        if event.payload.get("governance_phase") == "pre_generation":
            return _finding(
                finding_id=fid,
                event=event,
                evaluator_id=self.evaluator_id,
                code="CONTENT_SAFETY_NOT_YET_AVAILABLE",
                severity=FindingSeverity.INFO,
                verdict=PolicyVerdict.NOT_APPLICABLE,
                rationale="Generated-content safety is evaluated after governed generation.",
                sufficiency=EvidenceSufficiency.NOT_APPLICABLE,
                details={"governance_phase": "pre_generation"},
            )
        if self._checker is None:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="SAFETY_ASSESSMENT_UNAVAILABLE", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="No typed content-safety checker is configured.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"checker_configured": False},
            )
        try:
            result = self._checker.check_content(event.payload)
        except Exception as error:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="SAFETY_CHECK_FAILED", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="The content-safety checker failed.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"error_type": type(error).__name__},
            )
        if result is None or not isinstance(result, ContentSafetyResult):
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="SAFETY_RESULT_MISSING", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="The checker returned no typed safety result.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"safety_checked": False},
            )
        if not result.evaluated:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="SAFETY_NOT_EVALUATED", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="The content-safety check was not performed.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"evaluated": False, "safety_evaluator_id": result.evaluator_id},
            )
        safe = result.is_safe is True
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("CONTENT_SAFETY_PASSED" if safe else "CONTENT_SAFETY_VIOLATION"),
            severity=(FindingSeverity.INFO if safe else FindingSeverity.CRITICAL),
            verdict=(PolicyVerdict.COMPLIANT if safe else PolicyVerdict.NONCOMPLIANT),
            rationale=("Content passed typed safety evaluation." if safe else "Content failed typed safety evaluation."),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            details={
                "safety_breach": not safe,
                "finding_codes": result.finding_codes,
                "safety_evaluator_id": result.evaluator_id,
            },
        )


class ProjectCommercialControlEvaluator(_RecordBackedEvaluator):
    evaluator_id = "EVAL-PROJECT-COMMERCIAL-CONTROL"
    record_id = COMMERCIAL_PURCHASES_RECORD_ID
    ambiguous_code = "COMMERCIAL_RECORD_AMBIGUOUS"
    inactive_code = "COMMERCIAL_RECORD_INACTIVE"

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_comm", event, operation, record_registry)
        record, failure = self._load_record(fid, event, record_registry)
        if failure is not None:
            return failure
        amount_raw = event.payload.get("synthetic_purchase_amount")
        purchase_operation = operation.operation_id == "commercial_purchase_request"
        if purchase_operation and amount_raw is None:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="PURCHASE_AMOUNT_MISSING", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="The purchase amount is required for this operation.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                primary_records=(record.identity,), details={"amount_present": False},
            )
        if amount_raw is not None:
            if isinstance(amount_raw, bool) or not isinstance(amount_raw, (int, float)):
                return self._invalid_amount(fid, event, record.identity)
            amount = float(amount_raw)
            if not math.isfinite(amount) or amount < 0:
                return self._invalid_amount(fid, event, record.identity)
        else:
            amount = 0.0
        request_flag = event.payload.get("commercial_purchase_request", False)
        if type(request_flag) is not bool:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="PURCHASE_FLAG_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="commercial_purchase_request must be a strict Boolean.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                primary_records=(record.identity,), details={"valid": False},
            )
        commercial = request_flag or amount > 0 or purchase_operation
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("PROJECT_CONTROL_COMMERCIAL_DRIFT_HELD" if commercial else "COMMERCIAL_CONTROL_NOMINAL"),
            severity=(FindingSeverity.RESTRICTIVE if commercial else FindingSeverity.INFO),
            verdict=(PolicyVerdict.NONCOMPLIANT if commercial else PolicyVerdict.COMPLIANT),
            rationale=("A commercial request is held by project controls." if commercial else "No commercial activity was detected."),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            primary_records=(record.identity,),
            details={"commercial_attempt": commercial, "synthetic_purchase_amount": amount},
        )

    def _invalid_amount(self, fid, event, identity) -> PolicyFinding:
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code="INVALID_TRANSACTION_AMOUNT", severity=FindingSeverity.CRITICAL,
            verdict=PolicyVerdict.CONFIGURATION_FAILURE,
            rationale="The transaction amount must be finite and nonnegative.",
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            primary_records=(identity,), details={"amount_valid": False},
        )


class ChildSafeguardingEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-CHILD-SAFEGUARDING"

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_child_safe", event, operation, record_registry)
        if "learner_age" not in event.payload or event.payload["learner_age"] is None:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="LEARNER_AGE_MISSING", severity=FindingSeverity.WARNING,
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="learner_age is required for safeguarding evaluation.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"has_age": False},
            )
        age = event.payload["learner_age"]
        if isinstance(age, bool) or not isinstance(age, int) or not 1 <= age <= 130:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="LEARNER_AGE_MALFORMED", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="learner_age must be an integer between 1 and 130.",
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                details={"age_valid": False},
            )
        sdk = event.payload.get("commercial_sdk_active", False)
        purchase = event.payload.get("commercial_purchase_request", False)
        if type(sdk) is not bool or type(purchase) is not bool:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="COMMERCIAL_FLAG_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="Commercial indicators must be strict Booleans.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"commercial_flags_valid": False},
            )
        commercial = sdk or purchase or operation.operation_id == "commercial_purchase_request"
        exposure = age < 18 and commercial
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("CHILD_COMMERCIAL_EXPOSURE_HELD" if exposure else "CHILD_SAFEGUARDING_NOMINAL"),
            severity=(FindingSeverity.RESTRICTIVE if exposure else FindingSeverity.INFO),
            verdict=(PolicyVerdict.NONCOMPLIANT if exposure else PolicyVerdict.COMPLIANT),
            rationale=("Commercial exposure involving a minor is held." if exposure else "The event satisfies learner safeguarding controls."),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            details={"learner_age": age, "commercial": commercial},
        )


class ProjectTargetedAdControlEvaluator(_RecordBackedEvaluator):
    evaluator_id = "EVAL-PROJECT-TARGETED-AD-CONTROL"
    record_id = TARGETED_ADVERTISING_RECORD_ID
    ambiguous_code = "TARGETED_AD_RECORD_AMBIGUOUS"
    inactive_code = "TARGETED_AD_RECORD_INACTIVE"
    EXACT_SIGNAL = EXACT_PROHIBITED_INFERENCE_SIGNAL

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_ad", event, operation, record_registry)
        record, failure = self._load_record(fid, event, record_registry)
        if failure is not None:
            return failure
        ad_flag = event.payload.get("commercial_ad_delivery", False)
        if type(ad_flag) is not bool:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="TARGETED_AD_FLAG_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="commercial_ad_delivery must be a strict Boolean.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                primary_records=(record.identity,), details={"valid": False},
            )
        raw_signal = event.payload.get("simulated_prohibited_inference_signal", "")
        if not isinstance(raw_signal, str):
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="INFERENCE_SIGNAL_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="The inference signal must be a string.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                primary_records=(record.identity,), details={"valid": False},
            )
        targeted = operation.operation_id == "targeted_ad_dispatch" or ad_flag
        exact = raw_signal == self.EXACT_SIGNAL
        if targeted:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code=("PROJECT_CONTROL_PROFILING_AD_BLOCKED" if exact else "PROJECT_CONTROL_TARGETED_AD_OPERATION_PROHIBITED"),
                severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.NONCOMPLIANT,
                rationale="Targeted advertising is prohibited by project controls.",
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                primary_records=(record.identity,),
                details={"signal": raw_signal, "targeted_ad_operation": True},
            )
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code="TARGETED_AD_CONTROL_NOMINAL", severity=FindingSeverity.INFO,
            verdict=PolicyVerdict.COMPLIANT,
            rationale="No targeted-ad operation was detected.",
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            primary_records=(record.identity,), details={},
        )


class InferenceDataEvaluator(_BaseEvaluator):
    evaluator_id = "EVAL-INFERENCE-DATA"
    EXACT_SIGNAL = EXACT_PROHIBITED_INFERENCE_SIGNAL

    def evaluate(self, event, operation, record_registry) -> PolicyFinding:
        fid = self._begin("find_inf", event, operation, record_registry)
        diagnosis = event.payload.get("clinical_diagnosis", False)
        if type(diagnosis) is not bool:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="DIAGNOSIS_FLAG_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="clinical_diagnosis must be a strict Boolean.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"valid": False},
            )
        if diagnosis or "diagnostic_label" in event.payload:
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="PROHIBITED_DIAGNOSTIC_SUBSTITUTION", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.NONCOMPLIANT,
                rationale="Diagnostic classification is prohibited in the sandbox.",
                sufficiency=EvidenceSufficiency.SUFFICIENT,
                details={"clinical_diagnosis_asserted": True},
            )
        signal = event.payload.get("simulated_prohibited_inference_signal", "")
        if not isinstance(signal, str):
            return _finding(
                finding_id=fid, event=event, evaluator_id=self.evaluator_id,
                code="INFERENCE_SIGNAL_INVALID", severity=FindingSeverity.CRITICAL,
                verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                rationale="The inference signal must be a string.",
                sufficiency=EvidenceSufficiency.INSUFFICIENT,
                details={"valid": False},
            )
        prohibited = signal == self.EXACT_SIGNAL
        return _finding(
            finding_id=fid, event=event, evaluator_id=self.evaluator_id,
            code=("EXACT_PROHIBITED_SIGNAL_DETECTED" if prohibited else "INFERENCE_DATA_NOMINAL"),
            severity=(FindingSeverity.CRITICAL if prohibited else FindingSeverity.INFO),
            verdict=(PolicyVerdict.NONCOMPLIANT if prohibited else PolicyVerdict.COMPLIANT),
            rationale=("The exact prohibited inference signal was detected." if prohibited else "No prohibited inference markers were detected."),
            sufficiency=EvidenceSufficiency.SUFFICIENT,
            details={"prohibited_signal_detected": prohibited},
        )
