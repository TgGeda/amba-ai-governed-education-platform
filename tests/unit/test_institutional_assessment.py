from __future__ import annotations

import pytest

from amba_ai.institutional.assessment import (
    AssessmentConfidence,
    InstitutionalAssessment,
    InstitutionalObservation,
    ObservationStatus,
)
from amba_ai.scenarios.models import ScenarioConfigurationError, ScenarioStage, sha256_canonical


def observation():
    return InstitutionalObservation(
        observation_id="OBS-1",
        institution_id="education_authority",
        mandate_id="education_mandate",
        projection_id="PROJ-1",
        source_release_digest="a"*64,
        fact_ids=("FACT-1",),
        category="educational_purpose",
        status=ObservationStatus.OBSERVED,
        statement="Synthetic educational-purpose indicator.",
        rationale_codes=("EDUCATION_INDICATOR",),
    )


def assessment(**overrides):
    item=observation()
    values={
        "assessment_id":"ASSESS-1",
        "scenario_id":"SCENARIO-1",
        "stage":ScenarioStage.STAGE_1,
        "institution_id":"education_authority",
        "mandate_id":"education_mandate",
        "projection_id":"PROJ-1",
        "source_release_digest":"a"*64,
        "assessed_at":"2026-01-01T00:00:00Z",
        "assessed_fact_ids":("FACT-1",),
        "observations":(item,),
        "unresolved_questions":(),
        "confidence_status":AssessmentConfidence.HIGH,
        "limitations":("synthetic_only",),
        "metadata":{"governance_recommendation_created":False},
        "synthetic":True,
        "legal_effect":False,
    }
    values.update(overrides)
    payload={
        "assessment_id":values["assessment_id"],
        "scenario_id":values["scenario_id"],
        "stage":int(values["stage"]),
        "institution_id":values["institution_id"],
        "mandate_id":values["mandate_id"],
        "projection_id":values["projection_id"],
        "source_release_digest":values["source_release_digest"],
        "assessed_at":"2026-01-01T00:00:00+00:00",
        "assessed_fact_ids":list(values["assessed_fact_ids"]),
        "observations":[value.to_dict() for value in values["observations"]],
        "unresolved_questions":list(values["unresolved_questions"]),
        "confidence_status":values["confidence_status"].value,
        "limitations":list(values["limitations"]),
        "metadata":values["metadata"],
        "synthetic":values["synthetic"],
        "legal_effect":values["legal_effect"],
    }
    values["assessment_digest"]=sha256_canonical(payload)
    return InstitutionalAssessment(**values)


def test_assessment_is_immutable_and_canonical():
    value=assessment()
    assert value.to_canonical_json()
    with pytest.raises(TypeError): value.metadata["x"]=True


def test_observation_must_reference_assessed_fact():
    with pytest.raises(Exception): assessment(assessed_fact_ids=("OTHER",))


def test_assessment_rejects_governance_metadata():
    with pytest.raises(ScenarioConfigurationError): assessment(metadata={"recommended_action":"block"})


def test_assessment_remains_synthetic_without_legal_effect():
    with pytest.raises(ScenarioConfigurationError): assessment(synthetic=False)
    with pytest.raises(ScenarioConfigurationError): assessment(legal_effect=True)
