from __future__ import annotations
from pathlib import Path
import json, sys, yaml
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'src'))
from amba_ai.governance.thematic_evidence import VerifiedPassageCatalog,ThematicEvidenceResolver,load_definitions
CATALOG=ROOT/'kb/passages/verified_passage_catalog.json'
SETS=(
 ('cybersecurity_theme_passages.yaml','ethiopian_cybersecurity_policy_thematic_evidence_views'),
 ('esdp_vi_theme_passages.yaml','ethiopian_esdp_vi_historical_thematic_evidence_views'),
 ('unicef_theme_passages.yaml','unicef_ai_children_thematic_evidence_views'),
)
def write_pair(stem,payload):
 base=ROOT/'kb/records'/stem
 base.with_suffix('.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 base.with_suffix('.yaml').write_text(yaml.safe_dump(payload,allow_unicode=True,sort_keys=False,width=110),encoding='utf-8')
def main():
 catalog=VerifiedPassageCatalog.from_file(CATALOG); resolver=ThematicEvidenceResolver(catalog); gaps=[]
 for mapping,stem in SETS:
  views=[]
  for definition in load_definitions(ROOT/'kb/mappings'/mapping):
   view,new_gaps=resolver.resolve(definition); views.append(view.to_dict()); gaps.extend(g.to_dict() for g in new_gaps)
  payload={'schema_version':'1.0.0','record_type':'derived_thematic_evidence_views','mapping_file':f'kb/mappings/{mapping}','catalog_file':'kb/passages/verified_passage_catalog.json','views':views}
  write_pair(stem,payload)
 gap_payload={'schema_version':'1.0.0','gap_is_legal_violation':False,'gaps':gaps}
 gp=ROOT/'kb/gaps/policy_gaps.yaml'; gp.parent.mkdir(parents=True,exist_ok=True); gp.write_text(yaml.safe_dump(gap_payload,allow_unicode=True,sort_keys=False,width=110),encoding='utf-8')
 rp=ROOT/'docs/evidence/thematic_evidence_gap_report.md'; rp.parent.mkdir(parents=True,exist_ok=True)
 lines=['# Thematic Evidence Gap Report','',f'Reportable gaps: {len(gaps)}','']
 for g in gaps: lines += [f"## {g['subject']}",f"- Gap ID: `{g['gap_id']}`",f"- Evidence status: `{g['evidence_status']}`",f"- Disposition: `{g['disposition']}`",f"- Recommended action: {g['recommended_action']}",'']
 rp.write_text('\n'.join(lines),encoding='utf-8')
 print(f'thematic_view_sets={len(SETS)}'); print(f'reportable_gaps={len(gaps)}')
if __name__=='__main__': main()
