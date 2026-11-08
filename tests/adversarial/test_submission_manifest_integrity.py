from pathlib import Path
import json
from amba_ai.submission.manifest_verifier import verify_manifest
ROOT=Path(__file__).resolve().parents[2]
def test_tampered_artifact_is_detected(tmp_path:Path):
 manifest=json.loads((ROOT/'submission/artifacts/submission_manifest.json').read_text(encoding='utf-8'));target=manifest['entries'][0]['path'];source=ROOT/target;copy_root=tmp_path;dest=copy_root/target;dest.parent.mkdir(parents=True);dest.write_bytes(source.read_bytes()+b'\n')
 for entry in manifest['entries'][1:]:
  p=copy_root/entry['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/entry['path']).read_bytes())
 mp=copy_root/'manifest.json';mp.write_text(json.dumps(manifest),encoding='utf-8');result=verify_manifest(copy_root,mp);assert not result['valid'];assert any(x.startswith('hash_mismatch:') for x in result['failures'])
