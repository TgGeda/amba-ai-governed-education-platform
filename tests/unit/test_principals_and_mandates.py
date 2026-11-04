from __future__ import annotations

import secrets
import pytest

from amba_ai.governance.mandates import MandateDefinition, MandateRegistry
from amba_ai.governance.models import GovernanceConfigurationError
from amba_ai.governance.principals import PrincipalCredential, PrincipalRegistry, hash_secret_scrypt


@pytest.fixture
def salt():
    return secrets.token_hex(16)


@pytest.fixture
def principal_setup(salt):
    secret = "SchoolAdminSecret2026!"
    digest = hash_secret_scrypt(secret, salt)

    cred = PrincipalCredential(
        principal_id="PRINCIPAL-01",
        role="school_administrator",
        synthetic=True,
        legal_effect=False,
        credential_digest=digest,
        credential_algorithm="scrypt",
        credential_salt=salt,
        active_from="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        disabled_at=None,
        mandate_ids=("MANDATE-01",),
    )
    reg = PrincipalRegistry()
    reg.register(cred)
    return reg, cred, secret


def test_valid_secret_authenticates(principal_setup):
    reg, cred, secret = principal_setup
    assert reg.authenticate("PRINCIPAL-01", secret, "2026-06-01T00:00:00Z") is True


def test_stored_digest_rejected_as_token(principal_setup):
    reg, cred, _ = principal_setup
    assert reg.authenticate("PRINCIPAL-01", cred.credential_digest, "2026-06-01T00:00:00Z") is False


def test_wrong_secret_rejected(principal_setup):
    reg, _, _ = principal_setup
    assert reg.authenticate("PRINCIPAL-01", "WrongSecret", "2026-06-01T00:00:00Z") is False


def test_expired_principal_rejected(principal_setup):
    reg, _, secret = principal_setup
    assert reg.authenticate("PRINCIPAL-01", secret, "2027-01-02T00:00:00Z") is False


def test_disabled_principal_rejected(principal_setup):
    reg, _, secret = principal_setup
    reg.disable("PRINCIPAL-01", "2026-05-01T00:00:00Z")
    assert reg.authenticate("PRINCIPAL-01", secret, "2026-06-01T00:00:00Z") is False


def test_mandate_authorization_strict_checks():
    mandate = MandateDefinition(
        mandate_id="MANDATE-01",
        principal_id="PRINCIPAL-01",
        role="school_administrator",
        permitted_operations=("commercial_purchase_request",),
        permitted_decisions=("approve_review_queue", "deny_commercial_purchase"),
        synthetic=True,
        legal_effect=False,
        active_from="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        revoked_at=None,
    )
    reg = MandateRegistry()
    reg.register(mandate)

    assert reg.authorize(
        "MANDATE-01", "PRINCIPAL-01", "school_administrator",
        "commercial_purchase_request", "approve_review_queue", "2026-06-01T00:00:00Z"
    ) is True

    assert reg.authorize(
        "MANDATE-01", "PRINCIPAL-01", "compliance_officer",
        "commercial_purchase_request", "approve_review_queue", "2026-06-01T00:00:00Z"
    ) is False

    assert reg.authorize(
        "MANDATE-01", "PRINCIPAL-01", "school_administrator",
        "targeted_ad_dispatch", "approve_review_queue", "2026-06-01T00:00:00Z"
    ) is False

    assert reg.authorize(
        "MANDATE-01", "PRINCIPAL-01", "school_administrator",
        "commercial_purchase_request", "arbitrary_unpermitted_action", "2026-06-01T00:00:00Z"
    ) is False