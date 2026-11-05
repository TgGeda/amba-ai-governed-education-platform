from __future__ import annotations

import threading

from amba_ai.institutional.assessors.base import (
    InstitutionalAssessorProtocol,
)
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    require_identifier,
)


class InstitutionalAssessorRegistry:
    def __init__(self) -> None:
        self._by_institution: dict[
            str,
            InstitutionalAssessorProtocol,
        ] = {}
        self._institution_by_recipient: dict[str, str] = {}
        self._institution_by_mandate: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(
        self,
        assessor: InstitutionalAssessorProtocol,
    ) -> None:
        if not isinstance(
            assessor,
            InstitutionalAssessorProtocol,
        ):
            raise TypeError(
                "assessor must implement InstitutionalAssessorProtocol"
            )
        institution_id = require_identifier(
            assessor.institution_id,
            "institution_id",
        )
        recipient_id = require_identifier(
            assessor.recipient_id,
            "recipient_id",
        )
        mandate_id = require_identifier(
            assessor.mandate_id,
            "mandate_id",
        )
        with self._lock:
            existing = self._by_institution.get(
                institution_id
            )
            if existing is assessor:
                return
            if existing is not None:
                raise ScenarioConfigurationError(
                    "institution_id is already registered"
                )
            recipient_owner = (
                self._institution_by_recipient.get(
                    recipient_id
                )
            )
            if recipient_owner is not None:
                raise ScenarioConfigurationError(
                    "recipient_id is already assigned to "
                    f"institution {recipient_owner}"
                )
            mandate_owner = (
                self._institution_by_mandate.get(
                    mandate_id
                )
            )
            if mandate_owner is not None:
                raise ScenarioConfigurationError(
                    "mandate_id is already assigned to "
                    f"institution {mandate_owner}"
                )
            self._by_institution[institution_id] = assessor
            self._institution_by_recipient[
                recipient_id
            ] = institution_id
            self._institution_by_mandate[
                mandate_id
            ] = institution_id

    def get(
        self,
        institution_id: str,
    ) -> InstitutionalAssessorProtocol:
        normalized = require_identifier(
            institution_id,
            "institution_id",
        )
        with self._lock:
            assessor = self._by_institution.get(normalized)
        if assessor is None:
            raise KeyError(
                f"No assessor is registered for {normalized}"
            )
        return assessor

    def get_by_recipient(
        self,
        recipient_id: str,
    ) -> InstitutionalAssessorProtocol:
        normalized = require_identifier(
            recipient_id,
            "recipient_id",
        )
        with self._lock:
            institution_id = (
                self._institution_by_recipient.get(
                    normalized
                )
            )
            assessor = (
                None
                if institution_id is None
                else self._by_institution.get(
                    institution_id
                )
            )
        if assessor is None:
            raise KeyError(
                "No assessor is registered for recipient "
                f"{normalized}"
            )
        return assessor

    def get_by_mandate(
        self,
        mandate_id: str,
    ) -> InstitutionalAssessorProtocol:
        normalized = require_identifier(
            mandate_id,
            "mandate_id",
        )
        with self._lock:
            institution_id = (
                self._institution_by_mandate.get(
                    normalized
                )
            )
            assessor = (
                None
                if institution_id is None
                else self._by_institution.get(
                    institution_id
                )
            )
        if assessor is None:
            raise KeyError(
                "No assessor is registered for mandate "
                f"{normalized}"
            )
        return assessor

    def list_assessors(
        self,
    ) -> tuple[InstitutionalAssessorProtocol, ...]:
        with self._lock:
            return tuple(
                self._by_institution[key]
                for key in sorted(self._by_institution)
            )

    def institution_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._by_institution))

    def recipient_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(self._institution_by_recipient)
            )

    def mandate_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(self._institution_by_mandate)
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_institution)
