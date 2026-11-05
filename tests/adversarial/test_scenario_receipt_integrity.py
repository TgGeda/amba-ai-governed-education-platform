from __future__ import annotations

import inspect

from amba_ai.scenarios.invariant_verifier import ScenarioInvariantVerifier


def test_receipt_integrity_checks_are_fail_closed():
    source=inspect.getsource(ScenarioInvariantVerifier._verify_response)
    for expected in ("prevented distribution must not acknowledge","review routing must not acknowledge","trace execution receipt identity mismatch","trace review receipt identity mismatch","trace acknowledgment identity mismatch"):
        assert expected in source


def test_invariant_verifier_does_not_construct_operational_artifacts():
    source=inspect.getsource(ScenarioInvariantVerifier)
    for prohibited in ("ExecutionReceipt(","ReviewQueueReceipt(","DistributionAcknowledgment(","DistributionEffect(","PolicyRecommendation("):
        assert prohibited not in source
