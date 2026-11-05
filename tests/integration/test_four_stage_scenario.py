from __future__ import annotations

import inspect

from amba_ai.scenarios.demo_definition import SCENARIO_ID, STAGE_TIMESTAMPS
from amba_ai.scenarios.models import ScenarioStage
from amba_ai.scenarios.runner import FourStageScenarioRunner


def test_demo_timeline_has_exact_six_month_drift():
    assert STAGE_TIMESTAMPS[ScenarioStage.STAGE_1] == "2026-01-01T09:00:00Z"
    assert STAGE_TIMESTAMPS[ScenarioStage.STAGE_2] == "2026-07-01T09:00:00Z"
    assert STAGE_TIMESTAMPS[ScenarioStage.STAGE_3] == "2026-07-01T09:05:00Z"
    assert STAGE_TIMESTAMPS[ScenarioStage.STAGE_4] == "2026-07-01T09:10:00Z"


def test_demo_scenario_identity_is_stable():
    assert SCENARIO_ID == "SCENARIO-ETH-EDU-GOV-001-V1"


def test_runner_invokes_verified_services():
    source=inspect.getsource(FourStageScenarioRunner._execute_stage)
    for call in (
        "self._release.release(",
        "self._projection.project(",
        "self._coordination.coordinate(",
        "self._agent.run(",
        "self._invariants.verify(",
    ):
        assert call in source



def test_pipeline_event_flattens_evaluator_fields_without_losing_evidence():
    from amba_ai.scenarios.repository import ScenarioEventDefinition
    from amba_ai.scenarios.demo_definition import SCENARIO_ID
    from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioDestination
    from amba_ai.scenarios.models import ScenarioFact, ScenarioStage

    facts = (
        ScenarioFact(
            "FACT-A",
            SCENARIO_ID,
            ScenarioStage.STAGE_2,
            ("consumer_protection",),
            "purchase_interface",
            {
                "commercial_sdk_active": True,
                "transaction_amount_usd": 35.0,
                "learner_age": 14,
            },
        ),
    )
    event = ScenarioEventDefinition(
        "EVENT-A",
        "commercial_purchase_request",
        ScenarioStage.STAGE_2,
        "DEST-A",
        ("FACT-A",),
    )
    scenario = ScenarioDefinition(
        SCENARIO_ID,
        "Evaluator payload fixture",
        (ScenarioStage.STAGE_1, ScenarioStage.STAGE_2),
        (
            ScenarioFact(
                "FACT-BASE",
                SCENARIO_ID,
                ScenarioStage.STAGE_1,
                ("education",),
                "baseline",
                {},
            ),
            *facts,
        ),
        (ScenarioDestination("DEST-A", "review", "consumer_protection"),),
        (event,),
    )
    pipeline_event = FourStageScenarioRunner._pipeline_event(scenario, event)
    assert pipeline_event.payload["commercial_sdk_active"] is True
    assert pipeline_event.payload["transaction_amount_usd"] == 35.0
    assert pipeline_event.payload["learner_age"] == 14
    assert pipeline_event.payload["fact_ids"] == ("FACT-A",) or pipeline_event.payload["fact_ids"] == ["FACT-A"]
    assert pipeline_event.payload["facts"][0]["fact_id"] == "FACT-A"
