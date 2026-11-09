from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
def test_y3172_mapping_has_complete_unique_entries_and_claim_boundaries():
 p=yaml.safe_load((ROOT/'config/y3172_architecture_mapping.yaml').read_text(encoding='utf-8'));assert len(p['entries'])==13;assert len({x['mapping_id'] for x in p['entries']})==13;assert p['formal_conformance'] is False;assert p['itu_certification'] is False;assert all(x['runtime_evidence_pointers'] and x['limitations'] for x in p['entries'])
def test_agent_architecture_has_bounded_reusable_agents():
 p=yaml.safe_load((ROOT/'config/agent_responsibilities.yaml').read_text(encoding='utf-8'));assert len(p['agents'])==8;assert len({x['agent_id'] for x in p['agents']})==8;assert all(x['fail_closed_behavior'] and x['reusable_core'] and x['education_example'] and x['agriculture_example'] and x['finance_example'] for x in p['agents'])
