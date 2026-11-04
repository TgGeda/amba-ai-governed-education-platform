from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import re
import threading
from typing import Any, Iterator, Protocol

from amba_ai.governance.models import (
    GovernanceConfigurationError,
    to_canonical_json,
)


HEX_PATTERN = re.compile(r"^[0-9a-f]+$")
SCRYPT_ALGORITHM = "scrypt"
MINIMUM_SALT_BYTES = 16
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_DIGEST_HEX_LENGTH = SCRYPT_DKLEN * 2


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(field_name, str) or not field_name.strip():
        raise ValueError("field_name must not be empty")
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_lowercase_hex(
    value: object,
    field_name: str,
    *,
    exact_hex_characters: int | None = None,
    minimum_bytes: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a hexadecimal string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if HEX_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be lowercase hexadecimal")
    if len(normalized) % 2 != 0:
        raise ValueError(
            f"{field_name} must contain an even number of hexadecimal characters"
        )
    if exact_hex_characters is not None and len(normalized) != exact_hex_characters:
        raise ValueError(
            f"{field_name} must contain exactly "
            f"{exact_hex_characters} hexadecimal characters"
        )
    if minimum_bytes is not None and len(normalized) < minimum_bytes * 2:
        raise ValueError(
            f"{field_name} must contain at least {minimum_bytes} bytes "
            "encoded as lowercase hexadecimal"
        )
    return normalized


def parse_timestamp(value: str, field_name: str) -> datetime:
    normalized_field_name = _require_text(field_name, "field_name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{normalized_field_name} must be a nonempty ISO 8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(
            f"{normalized_field_name} must be a valid ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{normalized_field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class Clock(Protocol):
    def now_iso(self) -> str:
        ...


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class FixedClock:
    def __init__(self, fixed_iso: str) -> None:
        self._fixed = parse_timestamp(fixed_iso, "fixed_iso").isoformat()

    def now_iso(self) -> str:
        return self._fixed


def hash_secret_scrypt(secret: str, salt_hex: str) -> str:
    normalized_secret = _require_text(secret, "secret")
    normalized_salt = _require_lowercase_hex(
        salt_hex,
        "credential salt",
        minimum_bytes=MINIMUM_SALT_BYTES,
    )
    return hashlib.scrypt(
        normalized_secret.encode("utf-8"),
        salt=bytes.fromhex(normalized_salt),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    ).hex()


@dataclass(frozen=True, slots=True)
class PrincipalCredential:
    principal_id: str
    role: str
    synthetic: bool
    legal_effect: bool
    credential_digest: str
    credential_algorithm: str
    credential_salt: str
    active_from: str
    expires_at: str
    disabled_at: str | None
    mandate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        principal_id = _require_text(self.principal_id, "principal_id")
        role = _require_text(self.role, "role")
        algorithm = _require_text(
            self.credential_algorithm,
            "credential_algorithm",
        )
        if algorithm != SCRYPT_ALGORITHM:
            raise ValueError(
                f"credential_algorithm must be {SCRYPT_ALGORITHM}"
            )

        digest = _require_lowercase_hex(
            self.credential_digest,
            "credential_digest",
            exact_hex_characters=SCRYPT_DIGEST_HEX_LENGTH,
        )
        salt = _require_lowercase_hex(
            self.credential_salt,
            "credential_salt",
            minimum_bytes=MINIMUM_SALT_BYTES,
        )

        if type(self.synthetic) is not bool:
            raise TypeError("synthetic must be a strict Boolean")
        if type(self.legal_effect) is not bool:
            raise TypeError("legal_effect must be a strict Boolean")
        if self.synthetic and self.legal_effect:
            raise ValueError("Synthetic principal cannot claim legal effect")
        if not isinstance(self.mandate_ids, tuple):
            raise TypeError("mandate_ids must be a tuple")

        mandate_ids = tuple(
            str(value).strip()
            for value in self.mandate_ids
        )
        if not mandate_ids or any(not value for value in mandate_ids):
            raise ValueError("mandate_ids must not be empty")
        if len(mandate_ids) != len(set(mandate_ids)):
            raise ValueError("mandate_ids cannot contain duplicates")
        mandate_ids = tuple(sorted(mandate_ids))

        active = parse_timestamp(self.active_from, "active_from")
        expires = parse_timestamp(self.expires_at, "expires_at")
        if expires <= active:
            raise ValueError("expires_at must be later than active_from")

        disabled_iso: str | None = None
        if self.disabled_at is not None:
            disabled = parse_timestamp(self.disabled_at, "disabled_at")
            if disabled < active:
                raise ValueError("disabled_at cannot precede active_from")
            if disabled >= expires:
                raise ValueError("disabled_at must precede expires_at")
            disabled_iso = disabled.isoformat()

        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "credential_algorithm", algorithm)
        object.__setattr__(self, "credential_digest", digest)
        object.__setattr__(self, "credential_salt", salt)
        object.__setattr__(self, "active_from", active.isoformat())
        object.__setattr__(self, "expires_at", expires.isoformat())
        object.__setattr__(self, "disabled_at", disabled_iso)
        object.__setattr__(self, "mandate_ids", mandate_ids)

    def verify_secret(self, plaintext_secret: str) -> bool:
        if not isinstance(plaintext_secret, str) or not plaintext_secret:
            return False
        try:
            computed = hash_secret_scrypt(
                plaintext_secret,
                self.credential_salt,
            )
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(computed, self.credential_digest)

    def is_active(self, clock_iso: str) -> bool:
        now = parse_timestamp(clock_iso, "clock_iso")
        active = parse_timestamp(self.active_from, "active_from")
        expires = parse_timestamp(self.expires_at, "expires_at")
        if now < active or now >= expires:
            return False
        if self.disabled_at is not None:
            disabled = parse_timestamp(self.disabled_at, "disabled_at")
            if now >= disabled:
                return False
        return True

    def permits_mandate(self, mandate_id: str) -> bool:
        normalized = _require_text(mandate_id, "mandate_id")
        return normalized in self.mandate_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "role": self.role,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
            "credential_digest": self.credential_digest,
            "credential_algorithm": self.credential_algorithm,
            "credential_salt": self.credential_salt,
            "active_from": self.active_from,
            "expires_at": self.expires_at,
            "disabled_at": self.disabled_at,
            "mandate_ids": list(self.mandate_ids),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "role": self.role,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
            "credential_algorithm": self.credential_algorithm,
            "active_from": self.active_from,
            "expires_at": self.expires_at,
            "disabled_at": self.disabled_at,
            "mandate_ids": list(self.mandate_ids),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class PrincipalRegistry:
    def __init__(self) -> None:
        self._principals: dict[str, PrincipalCredential] = {}
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._principals)

    def __iter__(self) -> Iterator[PrincipalCredential]:
        return iter(self.list_all())

    def register(self, principal: PrincipalCredential) -> None:
        if not isinstance(principal, PrincipalCredential):
            raise TypeError("principal must be a PrincipalCredential")
        with self._lock:
            existing = self._principals.get(principal.principal_id)
            if existing is None:
                self._principals[principal.principal_id] = principal
                return
            if existing == principal:
                return
            raise GovernanceConfigurationError(
                "A principal with the same identifier has conflicting content"
            )

    def get(self, principal_id: str) -> PrincipalCredential | None:
        normalized = _require_text(principal_id, "principal_id")
        with self._lock:
            return self._principals.get(normalized)

    def require(self, principal_id: str) -> PrincipalCredential:
        normalized = _require_text(principal_id, "principal_id")
        with self._lock:
            principal = self._principals.get(normalized)
        if principal is None:
            raise GovernanceConfigurationError(
                "Required principal is not registered"
            )
        return principal

    def list_all(self) -> tuple[PrincipalCredential, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._principals.values(),
                    key=lambda value: value.principal_id,
                )
            )

    def authenticate(
        self,
        principal_id: str,
        plaintext_secret: str,
        clock_iso: str,
    ) -> bool:
        normalized = _require_text(principal_id, "principal_id")
        with self._lock:
            principal = self._principals.get(normalized)
        if principal is None or not principal.is_active(clock_iso):
            return False
        return principal.verify_secret(plaintext_secret)

    def disable(
        self,
        principal_id: str,
        disabled_at_iso: str,
    ) -> PrincipalCredential:
        normalized = _require_text(principal_id, "principal_id")
        disabled_at = parse_timestamp(
            disabled_at_iso,
            "disabled_at",
        ).isoformat()

        with self._lock:
            principal = self._principals.get(normalized)
            if principal is None:
                raise GovernanceConfigurationError(
                    "Required principal is not registered"
                )
            if principal.disabled_at is not None:
                if principal.disabled_at == disabled_at:
                    return principal
                raise GovernanceConfigurationError(
                    "Principal is already disabled at a different timestamp"
                )

            updated = PrincipalCredential(
                principal_id=principal.principal_id,
                role=principal.role,
                synthetic=principal.synthetic,
                legal_effect=principal.legal_effect,
                credential_digest=principal.credential_digest,
                credential_algorithm=principal.credential_algorithm,
                credential_salt=principal.credential_salt,
                active_from=principal.active_from,
                expires_at=principal.expires_at,
                disabled_at=disabled_at,
                mandate_ids=principal.mandate_ids,
            )
            self._principals[principal.principal_id] = updated
            return updated