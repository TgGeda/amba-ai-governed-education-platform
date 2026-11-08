from __future__ import annotations
from pathlib import Path
import json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def main():
 registry=json.loads((ROOT/'submission/artifacts/readiness_closure_evidence_registry.json').read_text(encoding='utf-8'));accepted=set(registry['accepted_metric_ids']);mapping=ROOT/'config/readiness_evidence_mapping.yaml';text=mapping.read_text(encoding='utf-8');updates=[]
 rules={'F5-M01':('F5','not_assessed','partially_demonstrated','AMBA-GOV-F5-OPEN-SOURCE-EVIDENCE-001'),'D11-M01':('D11','insufficient_evidence','partially_demonstrated','AMBA-GOV-D11-INCLUSION-EVIDENCE-001')}
 for metric,(finding,current,target,evidence_id) in rules.items():
  if metric not in accepted:continue
  pattern=rf'(^- \[{re.escape(finding)},.*?, ){re.escape(current)}(,.*?$)'
  text,count=re.subn(pattern,rf'\1{target}\2',text,count=1,flags=re.M)
  if count!=1:raise SystemExit(f'could not update {finding} from {current} to {target}')
  updates.append({'metric_id':metric,'finding_id':finding,'previous_status':current,'new_status':target,'evidence_id':evidence_id})
 if updates:mapping.write_text(text,encoding='utf-8',newline='\n');subprocess.run([sys.executable,str(ROOT/'tools/readiness/generate_readiness_reflection.py')],check=True,cwd=ROOT)
 out=ROOT/'submission/artifacts/readiness_closure_application.json';out.write_text(json.dumps({'schema_version':'1.0.0','accepted_metric_ids':sorted(accepted),'updates':updates,'refused_metric_ids':sorted(set(rules)-accepted)},ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8',newline='\n');print(f'updated_metric_ids={",".join(x["metric_id"] for x in updates)}');print(f'refused_metric_ids={",".join(sorted(set(rules)-accepted))}')
if __name__=='__main__':main()
