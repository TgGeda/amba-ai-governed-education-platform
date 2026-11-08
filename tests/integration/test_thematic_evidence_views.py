from pathlib import Path
import json,yaml
ROOT=Path(__file__).resolve().parents[2]
STEMS=('ethiopian_cybersecurity_policy_thematic_evidence_views','ethiopian_esdp_vi_historical_thematic_evidence_views','unicef_ai_children_thematic_evidence_views')
def test_views_reference_passages_without_copying_excerpts():
 catalog=json.loads((ROOT/'kb/passages/verified_passage_catalog.json').read_text(encoding='utf-8')); ids={x['passage_id'] for x in catalog['passages']}
 for stem in STEMS:
  j=json.loads((ROOT/'kb/records'/f'{stem}.json').read_text(encoding='utf-8')); y=yaml.safe_load((ROOT/'kb/records'/f'{stem}.yaml').read_text(encoding='utf-8')); assert j==y
  for v in j['views']:
   assert 'exact_source_excerpt' not in v and 'official_locator' not in v
   assert set(v['supporting_passage_ids'])<=ids
   if v['supporting_passage_ids']: assert v['provision_citation_eligible'] and not v['gap_ids']
   else: assert v['evidence_status']=='insufficient_evidence' and v['gap_ids']
def test_gap_is_in_report_and_yaml():
 gaps=yaml.safe_load((ROOT/'kb/gaps/policy_gaps.yaml').read_text(encoding='utf-8'))['gaps']; assert any(x['subject']=='commercial exploitation' for x in gaps)
 report=(ROOT/'docs/evidence/thematic_evidence_gap_report.md').read_text(encoding='utf-8'); assert 'commercial exploitation' in report and 'Verify and register' in report
