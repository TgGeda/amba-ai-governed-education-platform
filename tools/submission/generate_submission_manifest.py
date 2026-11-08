from __future__ import annotations
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from amba_ai.submission.manifest_builder import build_manifest
from amba_ai.submission.manifest_verifier import verify_manifest

def main():
    manifest=build_manifest(ROOT,ROOT/'config/submission_artifact_requirements.yaml');path=ROOT/'submission/artifacts/submission_manifest.json';text=json.dumps(manifest.to_dict(),ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n';path.write_text(text,encoding='utf-8',newline='\n');result=verify_manifest(ROOT,path)
    if not result['valid']:raise SystemExit(f"manifest verification failed: {result['failures']}")
    print(f"entry_count={result['entry_count']}");print(f"pending_gates={','.join(manifest.pending_gates)}");print(f"manifest_sha256={result['manifest_sha256']}")
if __name__=='__main__':main()
