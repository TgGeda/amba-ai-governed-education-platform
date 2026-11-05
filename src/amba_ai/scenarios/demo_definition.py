from __future__ import annotations

from amba_ai.governance.operation_registry import DestinationRegistry, OperationRegistry
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage
from amba_ai.scenarios.repository import (
    ScenarioDefinition,
    ScenarioDestination,
    ScenarioEventDefinition,
)

SCENARIO_ID = "SCENARIO-ETH-EDU-GOV-001-V1"
STAGE_TIMESTAMPS = {
    ScenarioStage.STAGE_1: "2026-01-01T09:00:00Z",
    ScenarioStage.STAGE_2: "2026-07-01T09:00:00Z",
    ScenarioStage.STAGE_3: "2026-07-01T09:05:00Z",
    ScenarioStage.STAGE_4: "2026-07-01T09:10:00Z",
}


def create_four_stage_education_scenario(
    *,
    operation_registry: OperationRegistry,
    destination_registry: DestinationRegistry,
) -> ScenarioDefinition:
    if not isinstance(operation_registry, OperationRegistry):
        raise TypeError("operation_registry must be an OperationRegistry")
    if not isinstance(destination_registry, DestinationRegistry):
        raise TypeError("destination_registry must be a DestinationRegistry")
    operations = (
        "classroom_exercise_telemetry",
        "commercial_purchase_request",
        "classroom_instruction_delivery",
        "targeted_ad_dispatch",
    )
    for operation_id in operations:
        operation_registry.require(operation_id)
    used_destinations: set[str] = set()
    destination_ids_list: list[str] = []
    for operation_id in operations:
        destination_id = _destination_for_operation(
            destination_registry,
            operation_id,
            used_destinations,
        )
        used_destinations.add(destination_id)
        destination_ids_list.append(destination_id)
    destination_ids = tuple(destination_ids_list)
    destinations = tuple(
        sorted(
            (
                ScenarioDestination(
                    destination_id=destination_id,
                    destination_type=destination_registry.require(destination_id).destination_class,
                    recipient_id=_recipient_for_operation(operation_id),
                )
                for operation_id, destination_id in zip(operations, destination_ids, strict=True)
            ),
            key=lambda item: item.destination_id,
        )
    )
    facts = tuple(
        sorted(
            (
                ScenarioFact(
                    "FACT-01-NOMINAL-CLASSROOM",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_1,
                    ("education",),
                    "classroom_use",
                    {
                        "educational_purpose": True,
                        "teacher_supervised": True,
                        "grade_level": 8,
                        "learner_age": 14,
                        "commercial_sdk_active": False,
                        "targeted_advertising": False,
                    },
                ),
                ScenarioFact(
                    "FACT-02-COMMERCIAL-DRIFT",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_2,
                    ("consumer_protection",),
                    "purchase_interface",
                    {
                        "purchase_interface_visible": True,
                        "synthetic_purchase_amount": 35.0,
                        "transaction_amount_usd": 35.0,
                        "learner_age": 14,
                        "parent_consent_on_file": False,
                        "commercial_sdk_origin": "SYNTHETIC-VENDOR-SDK",
                        "commercial_sdk_active": True,
                    },
                ),
                ScenarioFact(
                    "FACT-03-EDUCATION-REVIEW",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_3,
                    ("education",),
                    "commercial_signal",
                    {
                        "curriculum_alignment": True,
                        "commercial_sdk_active": True,
                        "teacher_review_required": True,
                        "learner_age": 14,
                    },
                ),
                ScenarioFact(
                    "FACT-04-DATA-PROTECTION-REVIEW",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_3,
                    ("data_protection",),
                    "personal_data",
                    {
                        "learner_data": True,
                        "profiling": True,
                        "processing_purpose_verified": False,
                        "learner_age": 14,
                    },
                ),
                ScenarioFact(
                    "FACT-05-CONSUMER-REVIEW",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_3,
                    ("consumer_protection",),
                    "consumer_disclosure",
                    {
                        "commercial_sdk_active": True,
                        "purchase_interface_visible": True,
                        "disclosure_reviewed": False,
                        "transaction_amount_usd": 35.0,
                        "synthetic_purchase_amount": 35.0,
                        "learner_age": 14,
                    },
                ),
                ScenarioFact(
                    "FACT-06-PROHIBITED-PROFILING",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_4,
                    ("data_protection",),
                    "targeted_advertising",
                    {
                        "commercial_ad_delivery": True,
                        "targeted_advertising": True,
                        "learner_profile_used": True,
                        "learner_age": 14,
                        "simulated_prohibited_inference_signal": (
                            "simulated_prohibited_inference_signal_v1"
                        ),
                    },
                ),
                ScenarioFact(
                    "FACT-07-ADVERTISING-DISCLOSURE",
                    SCENARIO_ID,
                    ScenarioStage.STAGE_4,
                    ("consumer_protection",),
                    "targeted_advertising",
                    {
                        "advertising_tracking_id": "SYNTHETIC-AD-CAMPAIGN-001",
                        "disclosure_present": False,
                        "commercial_ad_delivery": True,
                        "learner_age": 14,
                        "simulated_prohibited_inference_signal": (
                            "simulated_prohibited_inference_signal_v1"
                        ),
                    },
                ),
            ),
            key=lambda item: (int(item.release_stage), item.fact_id),
        )
    )
    events = (
        ScenarioEventDefinition(
            "EVENT-STAGE-1-CLASSROOM",
            operations[0],
            ScenarioStage.STAGE_1,
            destination_ids[0],
            ("FACT-01-NOMINAL-CLASSROOM",),
        ),
        ScenarioEventDefinition(
            "EVENT-STAGE-2-COMMERCIAL-DRIFT",
            operations[1],
            ScenarioStage.STAGE_2,
            destination_ids[1],
            ("FACT-02-COMMERCIAL-DRIFT",),
        ),
        ScenarioEventDefinition(
            "EVENT-STAGE-3-INSTITUTIONAL-REVIEW",
            operations[1],
            ScenarioStage.STAGE_3,
            destination_ids[2],
            (
                "FACT-03-EDUCATION-REVIEW",
                "FACT-04-DATA-PROTECTION-REVIEW",
                "FACT-05-CONSUMER-REVIEW",
            ),
        ),
        ScenarioEventDefinition(
            "EVENT-STAGE-4-TARGETED-ADVERTISING",
            operations[3],
            ScenarioStage.STAGE_4,
            destination_ids[3],
            (
                "FACT-06-PROHIBITED-PROFILING",
                "FACT-07-ADVERTISING-DISCLOSURE",
            ),
        ),
    )
    return ScenarioDefinition(
        scenario_id=SCENARIO_ID,
        title=(
            "Synthetic Classroom Governance, Commercial Drift, "
            "Institutional Dissent, and Targeted Advertising Escalation"
        ),
        configured_stages=(
            ScenarioStage.STAGE_1,
            ScenarioStage.STAGE_2,
            ScenarioStage.STAGE_3,
            ScenarioStage.STAGE_4,
        ),
        facts=facts,
        destinations=destinations,
        events=events,
    )


def _destination_for_operation(
    registry: DestinationRegistry,
    operation_id: str,
    used_destinations: set[str],
) -> str:
    matches = tuple(
        item.destination_id
        for item in registry.list_destinations()
        if item.registered
        and item.synthetic
        and item.destination_id not in used_destinations
        and registry.is_allowed_for_operation(
            item.destination_id,
            operation_id,
        )
    )
    if not matches:
        raise ValueError(
            "No unused registered synthetic destination "
            f"allows operation {operation_id}"
        )
    return matches[0]


def _recipient_for_operation(operation_id: str) -> str:
    if operation_id in {
        "classroom_exercise_telemetry",
        "classroom_instruction_delivery",
    }:
        return "education"
    if operation_id == "commercial_purchase_request":
        return "consumer_protection"
    return "data_protection"
