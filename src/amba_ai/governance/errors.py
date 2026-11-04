from __future__ import annotations

from amba_ai.governance.models import GovernanceConfigurationError


class GovernanceEvidenceError(GovernanceConfigurationError):
    """Raised when governance evidence is unavailable or invalid."""


class GovernanceApplicabilityError(GovernanceConfigurationError):
    """Raised when policy applicability cannot be resolved safely."""


class GovernanceManifestError(GovernanceConfigurationError):
    """Raised when a manifest or artifact fails integrity validation."""


class GovernanceCitationError(GovernanceConfigurationError):
    """Raised when a citation cannot be resolved to eligible evidence."""
