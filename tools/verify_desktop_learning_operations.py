from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from amba_ai.application.composition import create_desktop
from amba_ai.governance.learning_operations import (
    LEARNING_METHOD_OPERATION_MAP,
    canonical_learning_operation,
)
from amba_ai.governance.models import (
    EnforcementAction,
    PipelineEvent,
)
from amba_ai.ui.governance_context import (
    desktop_governance_context,
)


OPERATIONS_TO_CHECK = (
    "summarize_document",
    "generate_notes",
    "generate_study_assets",
    "generate_flashcards",
    "generate_quiz",
    "tutor_retrieve",
    "tutor_answer",
    "export_summary",
    "copy_summary",
)


EXPECTED_DESTINATIONS = {
    "learning.summary.generate":
        "desktop.summary",
    "learning.notes.generate":
        "desktop.notes",
    "learning.flashcards.generate":
        "desktop.study",
    "learning.quiz.generate":
        "desktop.study",
    "learning.tutor.retrieve":
        "internal.retrieval",
    "learning.tutor.answer":
        "desktop.tutor",
    "learning.content.export":
        "local.export",
    "learning.content.copy":
        "local.clipboard",
}


# Add an operation only when a review hold is deliberately
# expected for the current fixture and policy configuration.
EXPECTED_REVIEW_HOLDS: frozenset[str] = frozenset()


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def describe_finding(finding: object) -> str:
    code = getattr(
        finding,
        "code",
        getattr(finding, "finding_id", "UNKNOWN"),
    )
    evaluator = getattr(
        finding,
        "evaluator_id",
        "UNKNOWN-EVALUATOR",
    )
    verdict = enum_value(
        getattr(finding, "verdict", "unknown")
    )
    sufficiency = enum_value(
        getattr(
            finding,
            "evidence_sufficiency",
            "unknown",
        )
    )
    rationale = str(
        getattr(finding, "rationale", "")
    ).strip()

    return (
        f"{code} | "
        f"evaluator={evaluator} | "
        f"verdict={verdict} | "
        f"evidence={sufficiency} | "
        f"rationale={rationale or 'NONE'}"
    )


def print_evaluation(
    *,
    label: str,
    method_name: str,
    operation_id: str,
    destination_id: str,
    action: EnforcementAction,
    findings: tuple[object, ...],
) -> None:
    print(f"[{label}] {method_name}")
    print(f"  Operation:   {operation_id}")
    print(f"  Destination: {destination_id}")
    print(f"  Action:      {enum_value(action)}")

    if findings:
        print("  Findings:")

        for finding in findings:
            print(
                f"    - {describe_finding(finding)}"
            )
    else:
        print("  Findings:    NONE")


def verify_desktop_learning_operations() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    desktop = None
    all_passed = True

    print("=" * 78)
    print(
        "AMBA-GOV DESKTOP LEARNING OPERATION "
        "PREFLIGHT CHECK"
    )
    print("=" * 78)

    try:
        desktop = create_desktop(
            project_root=repo_root
        )

        services = getattr(
            desktop,
            "services",
            None,
        )

        if services is None:
            raise RuntimeError(
                "create_desktop() did not return an "
                "object with a services attribute."
            )

        governance_service = getattr(
            services,
            "governance_service",
            None,
        )

        if governance_service is None:
            raise RuntimeError(
                "Application services do not expose "
                "governance_service."
            )

        for method_name in OPERATIONS_TO_CHECK:
            now_iso = datetime.now(
                timezone.utc
            ).isoformat()

            expected_operation = (
                LEARNING_METHOD_OPERATION_MAP.get(
                    method_name
                )
            )

            if not expected_operation:
                print(
                    f"[FAIL] {method_name}: not mapped "
                    "in LEARNING_METHOD_OPERATION_MAP"
                )
                all_passed = False
                print("-" * 78)
                continue

            try:
                canonical_operation = (
                    canonical_learning_operation(
                        method_name
                    )
                )
            except Exception as exc:
                print(
                    f"[FAIL] {method_name}: operation "
                    f"resolution failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                all_passed = False
                print("-" * 78)
                continue

            if (
                canonical_operation
                != expected_operation
            ):
                print(
                    f"[FAIL] {method_name}: canonical "
                    f"operation {canonical_operation!r} "
                    "does not match mapping "
                    f"{expected_operation!r}"
                )
                all_passed = False
                print("-" * 78)
                continue

            try:
                context = (
                    desktop_governance_context(
                        method_name,
                        document_id=1,
                    )
                )
            except Exception as exc:
                print(
                    f"[FAIL] {method_name}: context "
                    f"creation failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                all_passed = False
                print("-" * 78)
                continue

            expected_destination = (
                EXPECTED_DESTINATIONS.get(
                    canonical_operation
                )
            )

            if expected_destination is None:
                print(
                    f"[FAIL] {method_name}: no expected "
                    "destination registered for "
                    f"{canonical_operation}"
                )
                all_passed = False
                print("-" * 78)
                continue

            if (
                context.destination_id
                != expected_destination
            ):
                print(
                    f"[FAIL] {method_name}: destination "
                    f"{context.destination_id!r}; "
                    f"expected "
                    f"{expected_destination!r}"
                )
                all_passed = False
                print("-" * 78)
                continue

            basis = context.authorization_basis

            if basis is None:
                print(
                    f"[FAIL] {method_name}: "
                    "authorization basis is missing"
                )
                all_passed = False
                print("-" * 78)
                continue

            try:
                basis_valid = basis.is_valid(
                    purpose=canonical_operation,
                    operation=canonical_operation,
                    now_iso=now_iso,
                )
            except Exception as exc:
                print(
                    f"[FAIL] {method_name}: "
                    "authorization validation raised "
                    f"{type(exc).__name__}: {exc}"
                )
                all_passed = False
                print("-" * 78)
                continue

            if not basis_valid:
                print(
                    f"[FAIL] {method_name}: "
                    "authorization basis is invalid "
                    "or expired for "
                    f"{canonical_operation}"
                )
                all_passed = False
                print("-" * 78)
                continue

            event_id = (
                "PREFLIGHT-"
                f"{method_name.upper().replace('_', '-')}-"
                f"{uuid4().hex[:16].upper()}"
            )

            event = PipelineEvent(
                event_id=event_id,
                timestamp=now_iso,
                operation_id=canonical_operation,
                source_node=context.source_node,
                destination_id=(
                    context.destination_id
                ),
                payload_type="job_pre_gate",
                payload={
                    "job_operation": method_name,
                    "operation_id":
                        canonical_operation,
                    "governance_phase":
                        "pre_generation",
                    "document_id": 1,
                    "destination_id":
                        context.destination_id,
                    "source_node":
                        context.source_node,
                    "preflight": True,
                },
                authorization_basis=basis,
                synthetic_flag=context.synthetic,
            )

            try:
                evaluation = (
                    governance_service.evaluate(event)
                )
            except Exception as exc:
                print(
                    f"[ERROR] {method_name}: "
                    "evaluation raised "
                    f"{type(exc).__name__}: {exc}"
                )
                all_passed = False
                print("-" * 78)
                continue

            recommendation = getattr(
                evaluation,
                "recommendation",
                None,
            )

            if recommendation is None:
                print(
                    f"[ERROR] {method_name}: "
                    "evaluation has no recommendation"
                )
                all_passed = False
                print("-" * 78)
                continue

            action = getattr(
                recommendation,
                "recommended_action",
                None,
            )

            if action is None:
                print(
                    f"[ERROR] {method_name}: "
                    "recommendation has no action"
                )
                all_passed = False
                print("-" * 78)
                continue

            findings = tuple(
                getattr(
                    evaluation,
                    "findings",
                    (),
                )
            )

            if action is EnforcementAction.PROCEED:
                print_evaluation(
                    label="PASS",
                    method_name=method_name,
                    operation_id=(
                        canonical_operation
                    ),
                    destination_id=(
                        context.destination_id
                    ),
                    action=action,
                    findings=findings,
                )

            elif (
                action
                is EnforcementAction.HOLD_FOR_REVIEW
            ):
                expected = (
                    canonical_operation
                    in EXPECTED_REVIEW_HOLDS
                )

                print_evaluation(
                    label=(
                        "HOLD-EXPECTED"
                        if expected
                        else "HOLD-UNEXPECTED"
                    ),
                    method_name=method_name,
                    operation_id=(
                        canonical_operation
                    ),
                    destination_id=(
                        context.destination_id
                    ),
                    action=action,
                    findings=findings,
                )

                if not expected:
                    all_passed = False

            else:
                print_evaluation(
                    label="BLOCK",
                    method_name=method_name,
                    operation_id=(
                        canonical_operation
                    ),
                    destination_id=(
                        context.destination_id
                    ),
                    action=action,
                    findings=findings,
                )
                all_passed = False

            print("-" * 78)

    except Exception as exc:
        print(
            "[FATAL] Preflight initialization failed: "
            f"{type(exc).__name__}: {exc}"
        )
        return 2

    finally:
        if desktop is not None:
            close = getattr(
                desktop,
                "close",
                None,
            )

            if callable(close):
                close()
            else:
                services = getattr(
                    desktop,
                    "services",
                    None,
                )
                services_close = getattr(
                    services,
                    "close",
                    None,
                )

                if callable(services_close):
                    services_close()

    if all_passed:
        print(
            "[SUCCESS] All desktop learning "
            "operations received their expected "
            "preflight disposition."
        )
        return 0

    print(
        "[FAILURE] One or more desktop learning "
        "operations failed preflight."
    )
    return 1


if __name__ == "__main__":
    sys.exit(
        verify_desktop_learning_operations()
    )