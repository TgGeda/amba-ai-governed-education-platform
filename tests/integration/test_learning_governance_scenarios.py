from __future__ import annotations

from pathlib import Path

from amba_ai.application.service_container import ApplicationServices
from amba_ai.scenarios.learning_runner import (
    LearningGovernanceScenarioRunner,
    LearningScenarioOutcome,
)


def test_runner_requires_application_services() -> None:
    try:
        LearningGovernanceScenarioRunner(object())  # type: ignore[arg-type]
    except TypeError as error:
        assert "ApplicationServices" in str(error)
    else:
        raise AssertionError("Runner accepted a parallel or untyped composition.")


def test_runner_contains_no_parallel_composition_constructors() -> None:
    source = Path("src/amba_ai/scenarios/learning_runner.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "Database(",
        "FaissRAGEngine(",
        "RuntimeEducationGovernanceService(",
        "ProviderRegistry(",
    ):
        assert forbidden not in source


def test_artifact_writer_is_reproducible_contract(tmp_path: Path) -> None:
    runner = object.__new__(LearningGovernanceScenarioRunner)
    outcome = LearningScenarioOutcome(
        scenario_id="A",
        scenario_name="Approved Lesson",
        status="succeeded",
        operation_ids=("learning.tutor.answer",),
        document_id=1,
        source_digest="a" * 64,
        chunk_ids=(1,),
        approved_chunk_ids=(1,),
        excluded_chunk_ids=(),
        retrieved_chunk_ids=(1,),
        output_id="EDU-OUT-1",
        receipt_id="EDU-GOV-1",
        trace_id="EDU-TRACE-1",
        audit_receipt="EDU-GOV-AUDIT-1",
        sanitized_digest="b" * 64,
        disposition="display",
        delivered_sinks=("tutor_display",),
        sink_receipts=(),
        distribution_prevention_receipt=None,
        assertions={"passed": True},
        details={},
    )
    payload = runner.write_artifacts((outcome,), tmp_path)
    assert payload["application_services_graph"] is True
    assert payload["all_passed"] is True
    assert (tmp_path / "learning_governance_scenarios.json").is_file()
    assert (tmp_path / "learning_governance_scenarios.md").is_file()
    assert (tmp_path / "scenario_a_approved_lesson.json").is_file()


def test_commercial_scenario_has_no_delivery_call() -> None:
    source = Path("src/amba_ai/scenarios/learning_runner.py").read_text(
        encoding="utf-8"
    )
    block = source[
        source.index("    def run_scenario_d_commercial_influence") :
        source.index("    def write_artifacts")
    ]
    assert ".deliver(" not in block
    assert "learning_distribution_prevented" in block
    assert "learning_output_refused" in block
