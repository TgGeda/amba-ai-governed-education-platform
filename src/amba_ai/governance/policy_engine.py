from __future__ import annotations

from typing import Any, Iterable

from amba_ai.governance.evaluator_registry import EvaluatorRegistry
from amba_ai.governance.models import (
    BindingLevel,
    EnforcementAction,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    GovernanceError,
    GovernanceConfigurationError,
    IdentifierProvider,
    OperationProtectionClass,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyFinding,
    PolicyRecommendation,
    PolicyRecordAmbiguityError,
    PolicyVerdict,
    ResolvedOperation,
)
from amba_ai.governance.operation_registry import OperationRegistry
from amba_ai.governance.record_registry import PolicyRecordRegistry


POLICY_ENGINE_RESOLVER_ID = "POLICY_ENGINE_RESOLVER"
POLICY_ENGINE_RECORD_CHECK_ID = "POLICY_ENGINE_RECORD_CHECK"

_UNRESOLVED_VERDICTS = frozenset(
    {
        PolicyVerdict.INSUFFICIENT_EVIDENCE,
        PolicyVerdict.APPLICABILITY_UNRESOLVED,
        PolicyVerdict.CONFIGURATION_FAILURE,
        PolicyVerdict.POTENTIAL_GAP,
        PolicyVerdict.AMBIGUITY,
        PolicyVerdict.CONFLICT,
    }
)


def _require_dependency(
    value: Any,
    expected_type: type,
    field_name: str,
) -> None:
    if not isinstance(value, expected_type):
        raise TypeError(
            f"{field_name} must be a {expected_type.__name__}"
        )


def _normalize_unique_strings(
    values: Iterable[str],
) -> tuple[str, ...]:
    normalized: list[str] = []
    observed: set[str] = set()

    for value in values:
        text = str(value).strip()
        if text and text not in observed:
            normalized.append(text)
            observed.add(text)

    return tuple(sorted(normalized))


class PolicyEngine:
    def __init__(
        self,
        record_registry: PolicyRecordRegistry,
        operation_registry: OperationRegistry,
        evaluator_registry: EvaluatorRegistry,
        identifier_provider: IdentifierProvider,
    ) -> None:
        _require_dependency(
            record_registry,
            PolicyRecordRegistry,
            "record_registry",
        )
        _require_dependency(
            operation_registry,
            OperationRegistry,
            "operation_registry",
        )
        _require_dependency(
            evaluator_registry,
            EvaluatorRegistry,
            "evaluator_registry",
        )

        if identifier_provider is None:
            raise TypeError("identifier_provider is required")
        if not callable(
            getattr(identifier_provider, "new_id", None)
        ):
            raise TypeError(
                "identifier_provider must satisfy IdentifierProvider"
            )

        self.records = record_registry
        self.operations = operation_registry
        self.evaluators = evaluator_registry
        self.id_provider = identifier_provider

    def evaluate_pipeline_event(
        self,
        event: PipelineEvent,
    ) -> PolicyEvaluationBundle:
        if not isinstance(event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")

        operation = self.operations.get(event.operation_id)
        if operation is None:
            return self._unresolved_operation_bundle(event)

        findings = self._configuration_findings(
            event,
            operation,
        )
        findings.extend(
            self._evaluate_required_evaluators(
                event,
                operation,
            )
        )

        self._validate_finding_set(
            event,
            operation,
            findings,
        )

        recommendation = self._aggregate_findings(
            event.event_id,
            operation,
            findings,
        )
        unresolved_questions = _normalize_unique_strings(
            finding.rationale
            for finding in findings
            if finding.verdict in _UNRESOLVED_VERDICTS
        )

        return PolicyEvaluationBundle(
            event_id=event.event_id,
            operation=operation,
            findings=tuple(findings),
            recommendation=recommendation,
            unresolved_questions=unresolved_questions,
        )

    def _unresolved_operation_bundle(
        self,
        event: PipelineEvent,
    ) -> PolicyEvaluationBundle:
        finding = self._engine_finding(
            event=event,
            prefix="find_cfg",
            code="UNRESOLVED_OPERATION_CONFIG",
            severity=FindingSeverity.CRITICAL,
            verdict=PolicyVerdict.CONFIGURATION_FAILURE,
            evaluator_id=POLICY_ENGINE_RESOLVER_ID,
            rationale=(
                "The event operation is not registered. "
                "Evaluation failed closed."
            ),
            details={
                "unresolved_operation_id": event.operation_id,
            },
        )
        recommendation = PolicyRecommendation(
            recommendation_id=self.id_provider.new_id("rec_cfg"),
            event_id=event.event_id,
            recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
            mitigation_steps=(
                "Hold the event payload.",
                "Register the operation before reprocessing.",
            ),
            requires_approval=True,
            escalation_role="compliance_officer",
        )

        return PolicyEvaluationBundle(
            event_id=event.event_id,
            operation=None,
            findings=(finding,),
            recommendation=recommendation,
            unresolved_questions=(
                "The operation configuration must be resolved.",
            ),
        )

    def _configuration_findings(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
    ) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []

        for evaluator_id in operation.required_evaluator_ids:
            if evaluator_id not in self.evaluators:
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_missing_eval",
                        code="REQUIRED_EVALUATOR_UNREGISTERED",
                        severity=FindingSeverity.CRITICAL,
                        verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                        evaluator_id=evaluator_id,
                        rationale=(
                            "A required evaluator is not registered."
                        ),
                        details={
                            "missing_evaluator_id": evaluator_id,
                        },
                    )
                )

        for record_id in operation.required_policy_record_ids:
            try:
                record = self.records.get_active_by_record_id(
                    record_id
                )
            except PolicyRecordAmbiguityError:
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_ambig_rec",
                        code="REQUIRED_RECORD_AMBIGUOUS",
                        severity=FindingSeverity.CRITICAL,
                        verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                        evaluator_id=POLICY_ENGINE_RECORD_CHECK_ID,
                        rationale=(
                            "A required policy record has multiple "
                            "active versions."
                        ),
                        details={
                            "required_record_id": record_id,
                        },
                    )
                )
                continue

            if (
                record is None
                or not self.records.eligible_for_project_enforcement(
                    record.identity
                )
            ):
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_missing_rec",
                        code="REQUIRED_RECORD_INACTIVE",
                        severity=FindingSeverity.WARNING,
                        verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                        evaluator_id=POLICY_ENGINE_RECORD_CHECK_ID,
                        rationale=(
                            "A required policy record is missing, "
                            "inactive, or ineligible for enforcement."
                        ),
                        details={
                            "required_record_id": record_id,
                        },
                    )
                )

        return findings

    def _evaluate_required_evaluators(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
    ) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []

        for evaluator_id in operation.required_evaluator_ids:
            evaluator = self.evaluators.get(evaluator_id)
            if evaluator is None:
                continue

            try:
                finding = evaluator.evaluate(
                    event,
                    operation,
                    self.records,
                )
            except GovernanceError as error:
                findings.append(
                    self._evaluator_failure_finding(
                        event=event,
                        evaluator_id=evaluator_id,
                        code="EVALUATOR_CONFIGURATION_FAILURE",
                        error=error,
                    )
                )
                continue
            except Exception as error:
                findings.append(
                    self._evaluator_failure_finding(
                        event=event,
                        evaluator_id=evaluator_id,
                        code="EVALUATOR_INTERNAL_FAILURE",
                        error=error,
                    )
                )
                continue

            if not isinstance(finding, PolicyFinding):
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_eval_err",
                        code="EVALUATOR_OUTPUT_INVALID",
                        severity=FindingSeverity.CRITICAL,
                        verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                        evaluator_id=evaluator_id,
                        rationale=(
                            "A required evaluator returned an invalid "
                            "result type."
                        ),
                        details={
                            "evaluator_id": evaluator_id,
                            "returned_type": type(finding).__name__,
                        },
                    )
                )
                continue

            if finding.event_id != event.event_id:
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_eval_err",
                        code="EVALUATOR_EVENT_MISMATCH",
                        severity=FindingSeverity.CRITICAL,
                        verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                        evaluator_id=evaluator_id,
                        rationale=(
                            "A required evaluator returned a finding "
                            "for a different event."
                        ),
                        details={"evaluator_id": evaluator_id},
                    )
                )
                continue

            if finding.evaluator_id != evaluator_id:
                findings.append(
                    self._engine_finding(
                        event=event,
                        prefix="find_eval_err",
                        code="EVALUATOR_ID_MISMATCH",
                        severity=FindingSeverity.CRITICAL,
                        verdict=PolicyVerdict.CONFIGURATION_FAILURE,
                        evaluator_id=evaluator_id,
                        rationale=(
                            "A required evaluator returned a finding "
                            "under a different evaluator identifier."
                        ),
                        details={"evaluator_id": evaluator_id},
                    )
                )
                continue

            findings.append(finding)

        return findings

    def _evaluator_failure_finding(
        self,
        *,
        event: PipelineEvent,
        evaluator_id: str,
        code: str,
        error: Exception,
    ) -> PolicyFinding:
        return self._engine_finding(
            event=event,
            prefix="find_eval_err",
            code=code,
            severity=FindingSeverity.CRITICAL,
            verdict=PolicyVerdict.CONFIGURATION_FAILURE,
            evaluator_id=evaluator_id,
            rationale=(
                "A required evaluator could not complete "
                "deterministic evaluation."
            ),
            details={
                "evaluator_id": evaluator_id,
                "error_type": type(error).__name__,
            },
        )

    def _engine_finding(
        self,
        *,
        event: PipelineEvent,
        prefix: str,
        code: str,
        severity: FindingSeverity,
        verdict: PolicyVerdict,
        evaluator_id: str,
        rationale: str,
        details: dict[str, Any],
    ) -> PolicyFinding:
        return PolicyFinding(
            finding_id=self.id_provider.new_id(prefix),
            event_id=event.event_id,
            finding_code=code,
            basis_category=BindingLevel.PROJECT_CONTROL,
            severity=severity,
            verdict=verdict,
            evaluator_id=evaluator_id,
            primary_records=(),
            supporting_records=(),
            rationale=rationale,
            evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
            deterministic_result=True,
            applicability_details=details,
        )

    @staticmethod
    def _validate_finding_set(
        event: PipelineEvent,
        operation: ResolvedOperation,
        findings: list[PolicyFinding],
    ) -> None:
        finding_ids: set[str] = set()

        for finding in findings:
            if finding.event_id != event.event_id:
                raise GovernanceConfigurationError(
                    "Policy finding event does not match evaluation event"
                )
            if finding.finding_id in finding_ids:
                raise GovernanceConfigurationError(
                    "Policy evaluation produced duplicate finding IDs"
                )
            finding_ids.add(finding.finding_id)

        if operation.required_evaluator_ids and not findings:
            raise GovernanceConfigurationError(
                "Required evaluators produced no findings"
            )

    def _aggregate_findings(
        self,
        event_id: str,
        operation: ResolvedOperation,
        findings: list[PolicyFinding],
    ) -> PolicyRecommendation:
        recommendation_id = self.id_provider.new_id("rec")
        has_configuration_failure = any(
            finding.verdict == PolicyVerdict.CONFIGURATION_FAILURE
            for finding in findings
        )
        has_insufficient_evidence = any(
            finding.verdict
            in {
                PolicyVerdict.INSUFFICIENT_EVIDENCE,
                PolicyVerdict.APPLICABILITY_UNRESOLVED,
                PolicyVerdict.AMBIGUITY,
                PolicyVerdict.CONFLICT,
            }
            for finding in findings
        )
        has_critical_noncompliance = any(
            finding.severity == FindingSeverity.CRITICAL
            and finding.verdict == PolicyVerdict.NONCOMPLIANT
            for finding in findings
        )
        has_restrictive_noncompliance = any(
            finding.severity == FindingSeverity.RESTRICTIVE
            and finding.verdict == PolicyVerdict.NONCOMPLIANT
            for finding in findings
        )
        has_potential_gap = any(
            finding.verdict == PolicyVerdict.POTENTIAL_GAP
            for finding in findings
        )

        if (
            operation.protection_class
            == OperationProtectionClass.PROHIBITED_BY_PROJECT_CONTROL
        ):
            steps = [
                "Block the prohibited operation under project controls."
            ]
            if has_configuration_failure:
                steps.append(
                    "Remediate governance configuration failures."
                )
            if has_insufficient_evidence:
                steps.append(
                    "Resolve missing policy evidence prerequisites."
                )
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=EnforcementAction.BLOCK,
                steps=steps,
                requires_approval=False,
                escalation_role=None,
            )

        if has_configuration_failure:
            if operation.failure_behavior == FailureBehavior.BLOCK:
                action = EnforcementAction.BLOCK
            elif operation.failure_behavior == FailureBehavior.ABSTAIN:
                action = EnforcementAction.ABSTAIN
            elif operation.failure_behavior == FailureBehavior.PROCEED:
                action = EnforcementAction.HOLD_FOR_REVIEW
            else:
                action = EnforcementAction.HOLD_FOR_REVIEW

            requires_approval = action == EnforcementAction.HOLD_FOR_REVIEW
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=action,
                steps=(
                    "Remediate governance configuration failures "
                    "before reprocessing.",
                ),
                requires_approval=requires_approval,
                escalation_role=(
                    "compliance_officer"
                    if requires_approval
                    else None
                ),
            )

        if has_insufficient_evidence:
            action = (
                EnforcementAction.ABSTAIN
                if operation.protection_class
                in {
                    OperationProtectionClass.LOW_RISK,
                    OperationProtectionClass.UNPROTECTED,
                }
                else EnforcementAction.HOLD_FOR_REVIEW
            )
            requires_approval = action == EnforcementAction.HOLD_FOR_REVIEW
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=action,
                steps=(
                    "Resolve missing evidence before proceeding.",
                ),
                requires_approval=requires_approval,
                escalation_role=(
                    operation.approval_role
                    or "compliance_officer"
                    if requires_approval
                    else None
                ),
            )

        if has_critical_noncompliance:
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=EnforcementAction.BLOCK,
                steps=(
                    "Halt pipeline transmission immediately.",
                    "Prevent prohibited downstream side effects.",
                ),
                requires_approval=False,
                escalation_role=None,
            )

        if has_restrictive_noncompliance:
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=EnforcementAction.HOLD_FOR_REVIEW,
                steps=(
                    "Hold the event pending administrative review.",
                ),
                requires_approval=True,
                escalation_role=(
                    operation.approval_role
                    or "school_administrator"
                ),
            )

        if has_potential_gap:
            if operation.operation_id == "policy_exploration_search":
                action = EnforcementAction.ABSTAIN
                steps = (
                    "Suppress unverified assertions and return a "
                    "grounded notice.",
                )
            else:
                action = EnforcementAction.HOLD_FOR_REVIEW
                steps = (
                    "Verify referenced evidence before delivery.",
                )

            requires_approval = (
                action == EnforcementAction.HOLD_FOR_REVIEW
            )
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=action,
                steps=steps,
                requires_approval=requires_approval,
                escalation_role=(
                    operation.approval_role
                    or "compliance_officer"
                    if requires_approval
                    else None
                ),
            )

        if operation.approval_required:
            return self._recommendation(
                recommendation_id=recommendation_id,
                event_id=event_id,
                action=EnforcementAction.REQUIRE_APPROVAL,
                steps=(
                    "Obtain the configured approval before execution.",
                ),
                requires_approval=True,
                escalation_role=operation.approval_role,
            )

        return self._recommendation(
            recommendation_id=recommendation_id,
            event_id=event_id,
            action=EnforcementAction.PROCEED,
            steps=(),
            requires_approval=False,
            escalation_role=None,
        )

    @staticmethod
    def _recommendation(
        *,
        recommendation_id: str,
        event_id: str,
        action: EnforcementAction,
        steps: Iterable[str],
        requires_approval: bool,
        escalation_role: str | None,
    ) -> PolicyRecommendation:
        return PolicyRecommendation(
            recommendation_id=recommendation_id,
            event_id=event_id,
            recommended_action=action,
            mitigation_steps=_normalize_unique_strings(steps),
            requires_approval=requires_approval,
            escalation_role=escalation_role,
        )
