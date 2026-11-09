from pathlib import Path
import hashlib,json,yaml
ROOT=Path(__file__).resolve().parents[2]
def main():
 cfg=yaml.safe_load((ROOT/'config/agent_responsibilities.yaml').read_text(encoding='utf-8'));agents=cfg['agents'];ids=[x['agent_id'] for x in agents]
 if len(agents)!=8 or len(ids)!=len(set(ids)):raise SystemExit('agent architecture requires 8 unique agents')
 for a in agents:
  missing=sorted(p for p in a['implementation_files'] if not (ROOT/p).exists())
  if missing:raise SystemExit(f"{a['agent_id']} missing implementation paths: {missing}")
  for key in ('inputs','outputs','fail_closed_behavior','reusable_core','domain_specific_configuration'):
   if not a[key]:raise SystemExit(f"{a['agent_id']} missing {key}")
 payload={'schema_version':cfg['schema_version'],'artifact_type':'agent_architecture','architecture_id':cfg['architecture_id'],'architecture_type':cfg['architecture_type'],'agent_count':len(agents),'agents':agents,'claim_boundaries':{'agents_have_bounded_authority':True,'assessment_agents_can_execute':False,'recommendation_authorizes_execution':False,'human_approval_bypass_allowed':False}}
 out=ROOT/'submission/artifacts';out.mkdir(parents=True,exist_ok=True);text=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';(out/'agent_architecture.json').write_text(text,encoding='utf-8',newline='\n');lines=['# AMBA-GOV Agent Architecture','', '> Bounded multi-agent governance architecture. Assessment and evidence agents cannot approve, execute, or distribute actions.','']
 for a in agents:lines += [f"## {a['name']} · `{a['agent_id']}`",'',a['responsibility'],'',f"- Inputs: {', '.join(a['inputs'])}",f"- Outputs: {', '.join(a['outputs'])}",f"- Consumes from: {', '.join(a['interactions']['consumes_from'])}",f"- Produces for: {', '.join(a['interactions']['produces_for'])}",f"- Fail closed: {'; '.join(a['fail_closed_behavior'])}",f"- Reusable core: {', '.join(a['reusable_core'])}",f"- Domain configuration: {', '.join(a['domain_specific_configuration'])}",f"- Education: {a['education_example']}",f"- Agriculture: {a['agriculture_example']}",f"- Finance: {a['finance_example']}",'']
 (out/'agent_architecture.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n');print(f'agent_count={len(agents)}');print(f'sha256={hashlib.sha256(text.encode()).hexdigest()}')
if __name__=='__main__':main()
