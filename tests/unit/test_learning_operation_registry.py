from __future__ import annotations
from pathlib import Path
from amba_ai.governance.learning_operations import LEARNING_METHOD_OPERATION_MAP, LEARNING_OPERATIONS, canonical_learning_operation, require_learning_operation, runtime_learning_operation
from amba_ai.governance.mandates import MandateRegistry
from amba_ai.governance.operation_registry import DestinationRegistry, OperationRegistry

EXPECTED={"learning.document.ingest","learning.document.index","learning.document.replace","learning.document.delete","learning.tutor.retrieve","learning.tutor.answer","learning.summary.generate","learning.notes.generate","learning.flashcards.generate","learning.quiz.generate","learning.content.export","learning.content.copy","learning.review.decide","learning.output.revoke"}

def test_all_learning_operations_are_first_class_and_namespaced():
    assert set(LEARNING_OPERATIONS)==EXPECTED
    assert require_learning_operation("tutor_answer").operation_id=="learning.tutor.answer"
    assert canonical_learning_operation("tutor_answer_stream")=="learning.tutor.answer"
    assert canonical_learning_operation("generate_notes")=="learning.notes.generate"

def test_runtime_compatibility_is_centralized():
    assert runtime_learning_operation("learning.tutor.answer")=="tutor_answer"
    assert runtime_learning_operation("tutor_answer_stream")=="tutor_answer"

def test_yaml_operation_registry_matches_python_registry():
    registry=OperationRegistry.load_from_yaml(Path("config/operations.yaml"))
    assert EXPECTED <= {item.operation_id for item in registry.list_operations()}

def test_destinations_cover_every_allowed_learning_destination():
    registry=DestinationRegistry.load_from_yaml(Path("config/destinations.yaml"))
    for operation in LEARNING_OPERATIONS.values():
        for destination in operation.allowed_destinations:
            assert registry.is_allowed_for_operation(destination,operation.operation_id)

def test_mandates_cover_every_required_learning_role():
    registry=MandateRegistry.load_from_yaml(Path("config/agent_mandates.yaml"))
    mandates=registry.list_all()
    for operation in LEARNING_OPERATIONS.values():
        roles={m.role for m in mandates if operation.operation_id in m.permitted_operations}
        assert operation.required_roles <= roles

def test_job_governance_uses_central_mapping():
    from amba_ai.services.job_governance import JOB_OPERATION_MAP
    assert JOB_OPERATION_MAP is LEARNING_METHOD_OPERATION_MAP
