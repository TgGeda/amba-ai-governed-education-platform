from __future__ import annotations

from dataclasses import replace
import pytest

from amba_ai.scenarios.models import ScenarioFact, ScenarioStage
from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioDestination, ScenarioEventDefinition


def test_event_cannot_reference_future_fact_in_validated_scenario():
    assert ScenarioStage.STAGE_4 > ScenarioStage.STAGE_1


def test_definition_allows_repeated_operation_type_with_unique_events():
    facts = (
        ScenarioFact(
            "F1",
            "S",
            ScenarioStage.STAGE_1,
            ("education",),
            "baseline",
            {},
        ),
    )

    destinations = (
        ScenarioDestination(
            "D1",
            "sink",
            "education",
        ),
    )

    events = (
        ScenarioEventDefinition(
            "E1",
            "O1",
            ScenarioStage.STAGE_1,
            "D1",
            ("F1",),
        ),
        ScenarioEventDefinition(
            "E2",
            "O1",
            ScenarioStage.STAGE_1,
            "D1",
            ("F1",),
        ),
    )

    definition = ScenarioDefinition(
        "S",
        "Repeated operation type",
        (ScenarioStage.STAGE_1,),
        facts,
        destinations,
        events,
    )

    assert tuple(
        event.event_id
        for event in definition.events
    ) == (
        "E1",
        "E2",
    )

    assert tuple(
        event.operation_id
        for event in definition.events
    ) == (
        "O1",
        "O1",
    )


def test_definition_rejects_non_synthetic_destination():
    with pytest.raises(Exception,match="synthetic"):
        ScenarioDestination("D1","sink","education",synthetic=False)

def test_definition_rejects_duplicate_event_identities():
    facts = (
        ScenarioFact(
            "F1",
            "S",
            ScenarioStage.STAGE_1,
            ("education",),
            "baseline",
            {},
        ),
    )

    destinations = (
        ScenarioDestination(
            "D1",
            "sink",
            "education",
        ),
    )

    events = (
        ScenarioEventDefinition(
            "E1",
            "O1",
            ScenarioStage.STAGE_1,
            "D1",
            ("F1",),
        ),
        ScenarioEventDefinition(
            "E1",
            "O1",
            ScenarioStage.STAGE_1,
            "D1",
            ("F1",),
        ),
    )

    with pytest.raises(
        Exception,
        match="event_id",
    ):
        ScenarioDefinition(
            "S",
            "Duplicate event identity",
            (ScenarioStage.STAGE_1,),
            facts,
            destinations,
            events,
        )
