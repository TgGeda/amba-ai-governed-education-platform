from __future__ import annotations

import json

import pytest

from amba_ai.readiness.verified_framework import (
    AssessmentMethod,
    AssessmentSubjectType,
    ReadinessFrameworkError,
    ReadinessStatus,
    ScoreStatus,
    load_reference_metric_catalog,
    verified_itu_ai_readiness_framework,
)


def _metric_payload() -> dict[str, object]:
    ids = [
        f"d{dimension}_m{metric:02d}"
        for dimension in range(1, 13)
        for metric in range(1, 9)
    ]
    ids.extend(f"d13_m{metric:02d}" for metric in range(1, 16))
    assert len(ids) == 111
    return {"dimensions": [{"metrics": [{"id": metric_id} for metric_id in ids]}]}


def _write_catalog(tmp_path, payload=None):
    path = tmp_path / "dimensions.json"
    path.write_text(json.dumps(payload or _metric_payload()), encoding="utf-8")
    return path


def test_verified_framework_preserves_exact_boundaries(tmp_path) -> None:
    path = _write_catalog(tmp_path)
    framework = verified_itu_ai_readiness_framework(path)
    assert len(framework.factors) == 6
    assert len(framework.dimensions) == 13
    assert len(framework.metric_catalog.metrics) == 111
    assert "d1_m01" in framework.metric_catalog.metric_ids
    assert "d13_m09" in framework.metric_catalog.metric_ids
    assert framework.dimension_to_factor_relationship == "many_to_many"
    assert framework.assessment_subject_type is AssessmentSubjectType.PROJECT
    assert framework.assessment_subject_id == "AMBA-GOV"
    assert framework.jurisdictional_context == "Ethiopia"
    assert framework.national_assessment is False
    assert framework.official_itu_certification is False
    assert framework.assessment_method is AssessmentMethod.PROJECT_LEVEL_SELF_EVALUATION
    assert framework.legal_determination_scope is False
    assert framework.overall_project_score is None
    assert framework.score_status is ScoreStatus.WITHHELD_PENDING_METHODOLOGY_AND_EVIDENCE_COVERAGE
    assert set(framework.permitted_statuses) == set(ReadinessStatus)


def test_metric_ids_are_preserved_and_grouped_by_dimension(tmp_path) -> None:
    catalog = load_reference_metric_catalog(_write_catalog(tmp_path))
    assert len(catalog.metric_ids) == len(set(catalog.metric_ids)) == 111
    assert tuple(catalog.by_dimension) == tuple(range(1, 14))
    assert sum(len(metrics) for metrics in catalog.by_dimension.values()) == 111


def test_catalog_rejects_metric_count_other_than_111(tmp_path) -> None:
    payload = _metric_payload()
    payload["dimensions"][0]["metrics"].pop()
    with pytest.raises(ReadinessFrameworkError, match="exactly 111"):
        load_reference_metric_catalog(_write_catalog(tmp_path, payload))


def test_catalog_rejects_missing_required_metric_examples(tmp_path) -> None:
    payload = _metric_payload()
    payload["dimensions"][0]["metrics"][0]["id"] = "d1_m99"
    with pytest.raises(ReadinessFrameworkError, match="d1_m01"):
        load_reference_metric_catalog(_write_catalog(tmp_path, payload))


def test_serialized_framework_withholds_score_and_weights(tmp_path) -> None:
    rendered = verified_itu_ai_readiness_framework(_write_catalog(tmp_path)).to_dict()
    assert rendered["factor_count"] == 6
    assert rendered["dimension_count"] == 13
    assert rendered["metric_count"] == 111
    assert rendered["overall_project_score"] is None
    assert rendered["score_status"] == "withheld_pending_methodology_and_evidence_coverage"
    assert rendered["assessment_scope"]["national_assessment"] is False
    assert rendered["assessment_scope"]["official_itu_certification"] is False
    assert rendered["weighting_status"] == {
        "metric": "methodology_unresolved",
        "factor": "methodology_unresolved",
        "dimension": "methodology_unresolved",
    }
    assert all(level["provenance"] == "reference_implementation" for level in rendered["maturity_levels"])
