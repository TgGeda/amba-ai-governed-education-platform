from __future__ import annotations

from pathlib import Path

from amba_ai.readiness.verified_framework import (
    ScoreStatus,
    verified_itu_ai_readiness_framework,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "readiness_reference_minimal"
    / "simulation"
    / "data"
    / "framework"
    / "dimensions.json"
)


def test_committed_reference_catalog_registers_exactly_111_metrics() -> None:
    framework = verified_itu_ai_readiness_framework(
        CATALOG_PATH,
        repository_root=REPOSITORY_ROOT,
    )
    assert len(framework.metric_catalog.metrics) == 111
    assert framework.metric_catalog.source_path == (
        "evidence/readiness_reference_minimal/simulation/data/framework/dimensions.json"
    )
    assert framework.metric_catalog.metric_ids[0] == "d1_m01"
    assert "d13_m09" in framework.metric_catalog.metric_ids
    assert framework.overall_project_score is None
    assert framework.score_status is ScoreStatus.WITHHELD_PENDING_METHODOLOGY_AND_EVIDENCE_COVERAGE
    assert framework.national_assessment is False
    assert framework.official_itu_certification is False
