from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
def test_mapping_never_claims_formal_conformance_or_certification():
 text=(ROOT/'config/y3172_architecture_mapping.yaml').read_text(encoding='utf-8').lower();assert 'formal_conformance: false' in text;assert 'itu_certification: false' in text;assert 'y.3172 compliant' not in text;assert 'itu certified' not in text
def test_agent_config_does_not_give_assessors_execution_authority():
 p=yaml.safe_load((ROOT/'config/agent_responsibilities.yaml').read_text(encoding='utf-8'));assessor=next(x for x in p['agents'] if x['agent_id']=='INSTITUTIONAL-ASSESSMENT-AGENTS');blob=str(assessor).lower();assert 'without recommendation, approval, execution, or distribution authority' in blob
