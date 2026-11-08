from pathlib import Path
import json,pytest
from amba_ai.readiness.evidence_requirement_validator import EvidenceRequirementValidationError,load_requirements,validate_against_scoring
ROOT=Path(__file__).resolve().parents[2]
def test_requirements_must_exactly_cover_unscored_metrics():
    readiness=json.loads((ROOT/'submission/artifacts/readiness_reflection.json').read_text(encoding='utf-8'));requirements=load_requirements(ROOT/'config/readiness_evidence_requirements.yaml');requirements['requirements'].pop('D11-M01')
    with pytest.raises(EvidenceRequirementValidationError,match='exactly cover'):validate_against_scoring(requirements,readiness['scoring'])
def test_threshold_reduction_is_rejected(tmp_path:Path):
    source=(ROOT/'config/readiness_evidence_requirements.yaml').read_text(encoding='utf-8').replace('prohibit_threshold_reduction: true','prohibit_threshold_reduction: false');path=tmp_path/'requirements.yaml';path.write_text(source,encoding='utf-8')
    with pytest.raises(EvidenceRequirementValidationError,match='threshold reduction'):load_requirements(path)
