from pathlib import Path
from amba_ai.services.job_governance import JobGovernanceContext
from amba_ai.ui.governance_context import DesktopGovernanceContextFactory, verify_desktop_governance_contracts


def test_factory_returns_correlated_contexts():
    f = DesktopGovernanceContextFactory(session_id="desktop-test")
    a = f.for_operation("generate_notes", document_id=1)
    b = f.for_operation("tutor_answer", document_id=1)
    assert isinstance(a, JobGovernanceContext)
    assert a.run_id != b.run_id
    assert a.scenario_id == b.scenario_id == "desktop-learning-session"
    assert a.destination_id == "desktop.notes"
    assert b.destination_id == "desktop.tutor"
    assert a.authorization_basis is not None
    assert b.authorization_basis is not None
    assert a.authorization_basis.processing_operations == ("learning.notes.generate",)
    assert b.authorization_basis.processing_operations == ("learning.tutor.answer",)
    assert a.synthetic is True


def test_every_learning_job_call_has_context():
    root = Path("src/amba_ai/ui/features")
    expected = {"summarizer": 1, "notes": 1, "study": 1, "tutor": 2}
    for name, count in expected.items():
        source = (root / name / f"{name}_manager.py").read_text(encoding="utf-8")
        assert source.count("governance_context=desktop_governance_context(") == count


def test_verify_desktop_governance_contracts_runs_cleanly():
    verify_desktop_governance_contracts()