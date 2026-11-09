from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    evidence_chain: dict[str, Any]
    agents: dict[str, Any]
    y3172: dict[str, Any]
    readiness: dict[str, Any]
    evidence_plan: dict[str, Any]
    closure_registry: dict[str, Any]
    manifest: dict[str, Any]
    manifest_verification: dict[str, Any]
    passages: dict[str, dict[str, Any]]
    @property
    def stages(self) -> tuple[dict[str, Any], ...]: return tuple(self.evidence_chain.get('stages', ()))
    @property
    def pending_gates(self) -> tuple[str, ...]: return tuple(self.manifest.get('pending_gates', ()))
    @property
    def manifest_state(self) -> str:
        if self.manifest_verification.get('valid'): return 'VALID'
        failures=self.manifest_verification.get('failures',())
        return 'STALE' if any('hash_mismatch:' in str(x) or 'size_mismatch:' in str(x) for x in failures) else 'INVALID'
