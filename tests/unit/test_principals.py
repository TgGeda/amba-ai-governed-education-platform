from __future__ import annotations

from datetime import datetime, timezone
import secrets
import threading

import pytest

from amba_ai.governance.models import (
    GovernanceConfigurationError,
    to_canonical_json,
)
from amba_ai.governance.principals import (
    FixedClock,
    MINIMUM_SALT_BYTES,
    PrincipalCredential,
    PrincipalRegistry,
    SCRYPT_ALGORITHM,
    SCRYPT_DIGEST_HEX_LENGTH,
    SystemClock,
    hash_secret_scrypt,
    parse_timestamp,
)


ACTIVE_FROM = "2026-01-01T00:00:00Z"
EXPIRES_AT = "2027-01-01T00:00:00Z"
ACTIVE_NOW = "2026-06-01T12:00:00Z"
DEFAULT_SECRET = "PrincipalSecret123!"
DEFAULT_SALT = "0123456789abcdef0123456789abcdef"


def make_principal(
    *,
    principal_id: str = "PRINCIPAL-01",
    role: str = "school_administrator",
    synthetic: bool = True,
    legal_effect: bool = False,
    secret: str = DEFAULT_SECRET,
    salt: str = DEFAULT_SALT,
    credential_digest: str | None = None,
    credential_algorithm: str = SCRYPT_ALGORITHM,
    active_from: str = ACTIVE_FROM,
    expires_at: str = EXPIRES_AT,
    disabled_at: str | None = None,
    mandate_ids: tuple[str, ...] = (
        "MANDATE-02",
        "MANDATE-01",
    ),
) -> PrincipalCredential:
    digest = credential_digest or hash_secret_scrypt(secret, salt)
    return PrincipalCredential(
        principal_id=principal_id,
        role=role,
        synthetic=synthetic,
        legal_effect=legal_effect,
        credential_digest=digest,
        credential_algorithm=credential_algorithm,
        credential_salt=salt,
        active_from=active_from,
        expires_at=expires_at,
        disabled_at=disabled_at,
        mandate_ids=mandate_ids,
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            "2026-06-01T12:00:00Z",
            datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        ),
        (
            "2026-06-01T14:00:00+02:00",
            datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        ),
        (
            " 2026-06-01T12:00:00+00:00 ",
            datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_parse_timestamp_normalizes_to_utc(
    value: str,
    expected: datetime,
) -> None:
    assert parse_timestamp(value, "timestamp") == expected


@pytest.mark.parametrize(
    "value, message",
    [
        ("", "must be a nonempty ISO 8601 timestamp"),
        ("   ", "must be a nonempty ISO 8601 timestamp"),
        ("not-a-date", "must be a valid ISO 8601 timestamp"),
        ("2026-06-01T12:00:00", "must be timezone-aware"),
    ],
)
def test_parse_timestamp_rejects_invalid_values(
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_timestamp(value, "timestamp")


def test_parse_timestamp_rejects_empty_field_name() -> None:
    with pytest.raises(ValueError, match="field_name must not be empty"):
        parse_timestamp(ACTIVE_NOW, " ")


def test_fixed_clock_is_normalized_and_stable() -> None:
    clock = FixedClock("2026-06-01T14:00:00+02:00")

    assert clock.now_iso() == "2026-06-01T12:00:00+00:00"
    assert clock.now_iso() == clock.now_iso()


def test_system_clock_returns_timezone_aware_utc_timestamp() -> None:
    value = SystemClock().now_iso()
    parsed = datetime.fromisoformat(value)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def test_hash_secret_scrypt_is_deterministic_and_salt_sensitive() -> None:
    first = hash_secret_scrypt(DEFAULT_SECRET, DEFAULT_SALT)
    replay = hash_secret_scrypt(DEFAULT_SECRET, DEFAULT_SALT)
    different_salt = hash_secret_scrypt(
        DEFAULT_SECRET,
        "fedcba9876543210fedcba9876543210",
    )

    assert first == replay
    assert first != different_salt
    assert len(first) == SCRYPT_DIGEST_HEX_LENGTH
    assert first == first.lower()


@pytest.mark.parametrize(
    "secret, salt, exception, message",
    [
        (123, DEFAULT_SALT, TypeError, "secret must be a string"),
        ("", DEFAULT_SALT, ValueError, "secret must not be empty"),
        (
            DEFAULT_SECRET,
            "ABCDEF0123456789ABCDEF0123456789",
            ValueError,
            "lowercase hexadecimal",
        ),
        (
            DEFAULT_SECRET,
            "xyz",
            ValueError,
            "lowercase hexadecimal",
        ),
        (
            DEFAULT_SECRET,
            "abc",
            ValueError,
            "even number",
        ),
        (
            DEFAULT_SECRET,
            "00" * (MINIMUM_SALT_BYTES - 1),
            ValueError,
            "at least 16 bytes",
        ),
    ],
)
def test_hash_secret_scrypt_rejects_invalid_inputs(
    secret: object,
    salt: str,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        hash_secret_scrypt(secret, salt)  # type: ignore[arg-type]


def test_principal_normalizes_fields_and_mandate_order() -> None:
    principal = make_principal(
        principal_id="  PRINCIPAL-01  ",
        role="  school_administrator  ",
        mandate_ids=(" MANDATE-02 ", " MANDATE-01 "),
    )

    assert principal.principal_id == "PRINCIPAL-01"
    assert principal.role == "school_administrator"
    assert principal.credential_algorithm == "scrypt"
    assert principal.active_from == "2026-01-01T00:00:00+00:00"
    assert principal.expires_at == "2027-01-01T00:00:00+00:00"
    assert principal.mandate_ids == ("MANDATE-01", "MANDATE-02")


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        ("principal_id", {"principal_id": " "}),
        ("role", {"role": " "}),
    ],
)
def test_principal_rejects_empty_identifiers(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        make_principal(**overrides)


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        ("synthetic", {"synthetic": 1}),
        ("legal_effect", {"legal_effect": 0}),
    ],
)
def test_principal_requires_strict_booleans(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match=f"{field_name} must be a strict Boolean"):
        make_principal(**overrides)


def test_principal_rejects_synthetic_legal_effect() -> None:
    with pytest.raises(
        ValueError,
        match="Synthetic principal cannot claim legal effect",
    ):
        make_principal(synthetic=True, legal_effect=True)


def test_principal_rejects_unsupported_algorithm() -> None:
    with pytest.raises(
        ValueError,
        match="credential_algorithm must be scrypt",
    ):
        make_principal(credential_algorithm="pbkdf2")


@pytest.mark.parametrize(
    "digest, message",
    [
        ("a" * 62, "exactly 64 hexadecimal characters"),
        ("A" * 64, "lowercase hexadecimal"),
        ("z" * 64, "lowercase hexadecimal"),
    ],
)
def test_principal_rejects_invalid_credential_digest(
    digest: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_principal(credential_digest=digest)


@pytest.mark.parametrize(
    "salt, message",
    [
        ("A" * 32, "lowercase hexadecimal"),
        ("z" * 32, "lowercase hexadecimal"),
        ("abc", "even number"),
        ("00" * 15, "at least 16 bytes"),
    ],
)
def test_principal_rejects_invalid_credential_salt(
    salt: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_principal(salt=salt, credential_digest="a" * 64)


def test_principal_requires_mandate_tuple() -> None:
    with pytest.raises(TypeError, match="mandate_ids must be a tuple"):
        make_principal(mandate_ids=["MANDATE-01"])  # type: ignore[arg-type]


def test_principal_rejects_empty_or_duplicate_mandates() -> None:
    with pytest.raises(ValueError, match="mandate_ids must not be empty"):
        make_principal(mandate_ids=(" ",))

    with pytest.raises(ValueError, match="mandate_ids cannot contain duplicates"):
        make_principal(mandate_ids=("MANDATE-01", "MANDATE-01"))


@pytest.mark.parametrize(
    "active_from, expires_at",
    [
        ("2027-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("2027-01-02T00:00:00Z", "2027-01-01T00:00:00Z"),
    ],
)
def test_principal_rejects_invalid_active_window(
    active_from: str,
    expires_at: str,
) -> None:
    with pytest.raises(ValueError, match="expires_at must be later than active_from"):
        make_principal(active_from=active_from, expires_at=expires_at)


@pytest.mark.parametrize(
    "disabled_at, message",
    [
        (
            "2025-12-31T23:59:59Z",
            "disabled_at cannot precede active_from",
        ),
        (
            "2027-01-01T00:00:00Z",
            "disabled_at must precede expires_at",
        ),
        (
            "2035-01-01T00:00:00Z",
            "disabled_at must precede expires_at",
        ),
    ],
)
def test_principal_rejects_invalid_disable_time(
    disabled_at: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_principal(disabled_at=disabled_at)


def test_principal_allows_immediate_disable() -> None:
    principal = make_principal(disabled_at=ACTIVE_FROM)

    assert principal.disabled_at == "2026-01-01T00:00:00+00:00"
    assert principal.is_active(ACTIVE_FROM) is False


@pytest.mark.parametrize(
    "clock_iso, expected",
    [
        ("2025-12-31T23:59:59Z", False),
        ("2026-01-01T00:00:00Z", True),
        (ACTIVE_NOW, True),
        ("2027-01-01T00:00:00Z", False),
    ],
)
def test_principal_active_window(
    clock_iso: str,
    expected: bool,
) -> None:
    assert make_principal().is_active(clock_iso) is expected


def test_principal_disable_boundary() -> None:
    principal = make_principal(disabled_at=ACTIVE_NOW)

    assert principal.is_active("2026-06-01T11:59:59Z") is True
    assert principal.is_active(ACTIVE_NOW) is False


def test_principal_verifies_secret() -> None:
    principal = make_principal()

    assert principal.verify_secret(DEFAULT_SECRET) is True
    assert principal.verify_secret("WrongSecret!") is False
    assert principal.verify_secret(123) is False  # type: ignore[arg-type]
    assert principal.verify_secret("") is False


def test_principal_mandate_membership() -> None:
    principal = make_principal()

    assert principal.permits_mandate("MANDATE-01") is True
    assert principal.permits_mandate("MANDATE-99") is False


def test_principal_serialization_and_public_redaction() -> None:
    principal = make_principal()
    persisted = principal.to_dict()
    public = principal.to_public_dict()

    assert persisted["credential_digest"] == principal.credential_digest
    assert persisted["credential_salt"] == principal.credential_salt
    assert "credential_digest" not in public
    assert "credential_salt" not in public
    assert principal.to_canonical_json() == to_canonical_json(persisted)


def test_registry_registration_lookup_iteration_and_order() -> None:
    registry = PrincipalRegistry()
    second = make_principal(principal_id="PRINCIPAL-02")
    first = make_principal(principal_id="PRINCIPAL-01")

    registry.register(second)
    registry.register(first)
    registry.register(first)

    assert len(registry) == 2
    assert registry.get("PRINCIPAL-01") == first
    assert registry.require("PRINCIPAL-02") == second
    assert registry.list_all() == (first, second)
    assert tuple(registry) == (first, second)


def test_registry_rejects_invalid_registration_type() -> None:
    with pytest.raises(TypeError, match="principal must be a PrincipalCredential"):
        PrincipalRegistry().register(object())  # type: ignore[arg-type]


def test_registry_rejects_conflicting_principal() -> None:
    registry = PrincipalRegistry()
    registry.register(make_principal())

    with pytest.raises(
        GovernanceConfigurationError,
        match="same identifier has conflicting content",
    ):
        registry.register(make_principal(role="different_role"))


def test_registry_require_rejects_missing_principal() -> None:
    with pytest.raises(
        GovernanceConfigurationError,
        match="Required principal is not registered",
    ):
        PrincipalRegistry().require("MISSING")


@pytest.mark.parametrize("method_name", ["get", "require", "authenticate", "disable"])
def test_registry_rejects_empty_principal_ids(method_name: str) -> None:
    registry = PrincipalRegistry()
    method = getattr(registry, method_name)

    with pytest.raises(ValueError, match="principal_id must not be empty"):
        if method_name == "authenticate":
            method(" ", DEFAULT_SECRET, ACTIVE_NOW)
        elif method_name == "disable":
            method(" ", ACTIVE_NOW)
        else:
            method(" ")


def test_registry_authentication() -> None:
    registry = PrincipalRegistry()
    registry.register(make_principal())

    assert registry.authenticate("PRINCIPAL-01", DEFAULT_SECRET, ACTIVE_NOW) is True
    assert registry.authenticate("PRINCIPAL-01", "WrongSecret!", ACTIVE_NOW) is False
    assert registry.authenticate("MISSING", DEFAULT_SECRET, ACTIVE_NOW) is False
    assert registry.authenticate(
        "PRINCIPAL-01",
        DEFAULT_SECRET,
        "2027-01-01T00:00:00Z",
    ) is False


def test_registry_disable_is_idempotent_for_same_timestamp() -> None:
    registry = PrincipalRegistry()
    registry.register(make_principal())

    first = registry.disable("PRINCIPAL-01", ACTIVE_NOW)
    replay = registry.disable("PRINCIPAL-01", ACTIVE_NOW)

    assert first == replay
    assert registry.require("PRINCIPAL-01") == first
    assert registry.authenticate("PRINCIPAL-01", DEFAULT_SECRET, ACTIVE_NOW) is False


def test_registry_disable_rejects_conflicting_timestamp() -> None:
    registry = PrincipalRegistry()
    registry.register(make_principal())
    registry.disable("PRINCIPAL-01", ACTIVE_NOW)

    with pytest.raises(
        GovernanceConfigurationError,
        match="already disabled at a different timestamp",
    ):
        registry.disable("PRINCIPAL-01", "2026-06-02T12:00:00Z")


def test_registry_disable_rejects_missing_principal() -> None:
    with pytest.raises(
        GovernanceConfigurationError,
        match="Required principal is not registered",
    ):
        PrincipalRegistry().disable("MISSING", ACTIVE_NOW)


def test_registry_iteration_uses_snapshot() -> None:
    registry = PrincipalRegistry()
    first = make_principal(principal_id="PRINCIPAL-01")
    second = make_principal(principal_id="PRINCIPAL-02")
    registry.register(first)

    iterator = iter(registry)
    registry.register(second)

    assert tuple(iterator) == (first,)
    assert tuple(registry) == (first, second)


def test_registry_concurrent_identical_registration() -> None:
    registry = PrincipalRegistry()
    principal = make_principal()
    failures: list[Exception] = []

    def register() -> None:
        try:
            registry.register(principal)
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=register) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(registry) == 1
    assert registry.require("PRINCIPAL-01") == principal


def test_registry_concurrent_same_timestamp_disable() -> None:
    registry = PrincipalRegistry()
    registry.register(make_principal())
    results: list[PrincipalCredential] = []
    failures: list[Exception] = []

    def disable() -> None:
        try:
            results.append(registry.disable("PRINCIPAL-01", ACTIVE_NOW))
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=disable) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(results) == 10
    assert all(result == results[0] for result in results)
    assert registry.require("PRINCIPAL-01").disabled_at == (
        "2026-06-01T12:00:00+00:00"
    )


def test_random_generated_salt_is_accepted() -> None:
    salt = secrets.token_hex(MINIMUM_SALT_BYTES)
    principal = make_principal(salt=salt)

    assert principal.credential_salt == salt
    assert principal.verify_secret(DEFAULT_SECRET) is True
