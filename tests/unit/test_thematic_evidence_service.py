from pathlib import Path
from amba_ai.services.thematic_evidence_service import ThematicEvidenceService
ROOT=Path(__file__).resolve().parents[2]
def service(): return ThematicEvidenceService(records_root=ROOT/'kb/records',gaps_path=ROOT/'kb/gaps/policy_gaps.yaml',routing_path=ROOT/'config/thematic_evidence_routing.yaml')
def test_stage_context_resolves_passages_and_gap():
 c=service().for_stage('STAGE-2'); assert 'GAP-COMMERCIAL-EXPLOITATION' in c.gap_ids; assert 'UNICEF-PRIVACY-BY-DESIGN' in c.passage_ids; assert not c.to_dict()['binding_finding_eligible']
def test_stage_context_is_deterministic(): assert service().for_stage('STAGE-1').to_dict()==service().for_stage('STAGE-1').to_dict()
