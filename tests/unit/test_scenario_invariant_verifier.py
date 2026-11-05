from __future__ import annotations

import inspect

from amba_ai.scenarios.invariant_verifier import ScenarioInvariantEvidence, ScenarioInvariantReport, ScenarioInvariantVerifier


def test_invariant_models_are_typed():
    assert "releases" in ScenarioInvariantEvidence.__dataclass_fields__
    assert "valid" in ScenarioInvariantReport.__dataclass_fields__


def test_verifier_exposes_only_verification_surface():
    public={name for name,value in inspect.getmembers(ScenarioInvariantVerifier) if callable(value) and not name.startswith("_")}
    assert public == {"verify"}


def test_verifier_contains_required_cross_layer_checks():
    source=inspect.getsource(ScenarioInvariantVerifier)
    for expected in ("future fact leaked","recipient scope broadened","NOT_REACHED sink","COMPLETED sink","NOT_ATTEMPTED execution","coordination did not preserve"):
        assert expected in source
