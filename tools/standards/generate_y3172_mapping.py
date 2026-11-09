from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from amba_ai.standards.y3172_mapping_service import build_y3172_mapping
def main():
 result=build_y3172_mapping(ROOT,ROOT/'config/y3172_architecture_mapping.yaml');out=ROOT/'submission/artifacts';out.mkdir(parents=True,exist_ok=True);text=json.dumps(result.payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';(out/'y3172_architecture_mapping.json').write_text(text,encoding='utf-8',newline='\n');lines=['# AMBA-GOV ITU-T Y.3172 Architecture Mapping','',f"> {result.payload['claim_boundary']}",'',f"Source artifact SHA-256: `{result.source_artifact_sha256}`",'']
 for x in result.payload['entries']:lines += [f"## {x['mapping_id']} · {x['project_component']}",'',f"**Y.3172 interpretation:** {x['y3172_interpretation']}",'',x['runtime_responsibility'],'',f"- Verified records: {', '.join(x['y3172_record_ids'])}",f"- Approved passages: {', '.join(x['approved_passage_ids'])}",f"- Implementation: {', '.join(x['implementation_files'])}",f"- Runtime evidence: {', '.join(x['runtime_evidence_pointers'])}",f"- Limitations: {'; '.join(x['limitations'])}",'']
 (out/'y3172_architecture_mapping.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n');print(f'entry_count={len(result.payload["entries"])}');print(f'sha256={hashlib.sha256(text.encode()).hexdigest()}')
if __name__=='__main__':main()
