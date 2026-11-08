from __future__ import annotations
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from amba_ai.submission.manifest_verifier import verify_manifest

def main():
 result=verify_manifest(ROOT,ROOT/'submission/artifacts/submission_manifest.json');print(json.dumps(result,ensure_ascii=False,sort_keys=True));raise SystemExit(0 if result['valid'] else 1)
if __name__=='__main__':main()
