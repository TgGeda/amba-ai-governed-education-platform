from pathlib import Path
import json
from amba_ai.readiness.open_source_evidence_validator import validate_open_source_evidence
from amba_ai.readiness.inclusion_evidence_validator import validate_inclusion_evidence
ROOT=Path(__file__).resolve().parents[2]
def test_open_source_evidence_fails_closed_without_license(tmp_path:Path):
 for name in ('CONTRIBUTING.md','CODE_OF_CONDUCT.md','SECURITY.md'):(tmp_path/name).write_text('policy',encoding='utf-8')
 (tmp_path/'submission/artifacts').mkdir(parents=True);(tmp_path/'submission/artifacts/sbom.cdx.json').write_text(json.dumps({'bomFormat':'CycloneDX','specVersion':'1.5','components':[]}),encoding='utf-8')
 result=validate_open_source_evidence(tmp_path,ROOT/'config/open_source_governance_requirements.yaml');assert result['acceptance_passed'] is False;assert result['target_status'] is None

def test_inclusion_evidence_never_accepts_pending_review(tmp_path:Path):
 for rel in ('docs/inclusion/accessibility_test_protocol.md','docs/inclusion/representative_review_protocol.md'):
  p=tmp_path/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('protocol',encoding='utf-8')
 out=tmp_path/'submission/artifacts';out.mkdir(parents=True);(out/'accessibility_evaluation.json').write_text(json.dumps({'formal_certification':False,'tested_criteria':['x'],'untested_criteria':['y']}),encoding='utf-8');(out/'offline_operation_evaluation.json').write_text(json.dumps({'completed':True,'scenarios':['offline']}),encoding='utf-8');(out/'representative_review_record.json').write_text(json.dumps({'completed':False,'personal_data_included':False,'scope':'','limitations':['pending'],'outcome_measures':[]}),encoding='utf-8');(out/'four_stage_evidence_chain.json').write_text('{}',encoding='utf-8')
 result=validate_inclusion_evidence(tmp_path,ROOT/'config/inclusion_evaluation_requirements.yaml');assert result['acceptance_passed'] is False;assert result['target_status'] is None
