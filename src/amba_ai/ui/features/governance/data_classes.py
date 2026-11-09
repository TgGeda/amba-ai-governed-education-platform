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
    passages: dict[str, dict[str, Any]]

    @property
    def stages(self) -> list[dict[str, Any]]:
        return list(self.evidence_chain.get("stages", []))

    @property
    def pending_gates(self) -> list[str]:
        return list(self.manifest.get("pending_gates", []))
