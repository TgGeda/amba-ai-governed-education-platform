from __future__ import annotations
from pathlib import Path
import hashlib,json
from .models import ReadinessReflection
def write_reports(reflection:ReadinessReflection,compact:Path,pretty:Path,markdown:Path)->str:
 payload=reflection.to_dict(); text=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';compact.parent.mkdir(parents=True,exist_ok=True);compact.write_text(text,encoding='utf-8',newline='\n');pretty.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')
 lines=['# AMBA-GOV Evidence-Bounded Readiness Reflection','',f"Evidence artifact SHA-256: `{payload['evidence_artifact']['sha256']}`",'', '> Project-level reflection only. This is not a national assessment, official ITU certification, formal Y.3172 conformance claim, or legal determination.','', '## Score boundary','', '- Overall project score: withheld','- Status: `withheld_pending_methodology_and_evidence_coverage`','', '## Findings','']
 for f in payload['findings']: lines += [f"### {f['framework_element_id']} · {f['framework_element_name']}",f"- Type: `{f['framework_element_type']}`",f"- Status: `{f['status']}`",f"- Rationale: {f['rationale']}",f"- Evidence pointers: {', '.join(f['evidence_pointers']) or 'none'}",f"- Approved passage IDs: {', '.join(f['passage_ids']) or 'none'}",f"- Y.3172 records: {', '.join(f['y3172_record_ids']) or 'none'}",f"- Limitations: {'; '.join(f['limitations']) or 'none'}",'']
 markdown.write_text('\n'.join(lines),encoding='utf-8',newline='\n');return hashlib.sha256(text.encode()).hexdigest()
