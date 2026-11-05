from __future__ import annotations

import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.assessors.consumer_protection_assessor import (
    ConsumerProtectionAssessor,
)
from amba_ai.institutional.assessors.data_protection_assessor import (
    DataProtectionAssessor,
)
from amba_ai.institutional.assessors.education_assessor import (
    EducationAssessor,
)
from amba_ai.institutional.registry import (
    InstitutionalAssessorRegistry,
)
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.models import ScenarioConfigurationError


def assessor(cls):
    return cls(
        identifier_provider=SequentialIdentifierProvider(),
        clock=DeterministicScenarioClock(
            initial_time="2026-01-01T00:00:00Z"
        ),
    )


def test_registry_returns_deterministic_order():
    registry=InstitutionalAssessorRegistry()
    registry.register(assessor(EducationAssessor))
    registry.register(assessor(DataProtectionAssessor))
    registry.register(assessor(ConsumerProtectionAssessor))
    assert tuple(item.institution_id for item in registry.list_assessors()) == tuple(sorted(registry.institution_ids()))


def test_registry_resolves_recipient_and_mandate():
    registry=InstitutionalAssessorRegistry(); value=assessor(EducationAssessor); registry.register(value)
    assert registry.get_by_recipient(value.recipient_id) is value
    assert registry.get_by_mandate(value.mandate_id) is value


def test_same_instance_registration_is_idempotent():
    registry=InstitutionalAssessorRegistry(); value=assessor(EducationAssessor); registry.register(value); registry.register(value)
    assert len(registry) == 1


def test_conflicting_institution_registration_fails_closed():
    registry=InstitutionalAssessorRegistry(); registry.register(assessor(EducationAssessor))
    with pytest.raises(ScenarioConfigurationError,match="institution_id"):
        registry.register(assessor(EducationAssessor))


def test_missing_recipient_registration_fails_closed():
    registry=InstitutionalAssessorRegistry()
    with pytest.raises(KeyError): registry.get_by_recipient("education")
