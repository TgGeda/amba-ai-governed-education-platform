from pathlib import Path
import json
from amba_ai.readiness.open_source_evidence_validator import validate_open_source_evidence
ROOT=Path(__file__).resolve().parents[2]
def test_placeholder_license_is_rejected(tmp_path:Path):
 for name,text in {'LICENSE':'Choose a license','CONTRIBUTING.md':'x','CODE_OF_CONDUCT.md':'x','SECURITY.md':'x'}.items():(tmp_path/name).write_text(text,encoding='utf-8')
 p=tmp_path/'submission/artifacts';p.mkdir(parents=True);(p/'sbom.cdx.json').write_text(json.dumps({'bomFormat':'CycloneDX','specVersion':'1.5','components':[]}),encoding='utf-8')
 assert validate_open_source_evidence(tmp_path,ROOT/'config/open_source_governance_requirements.yaml')['acceptance_passed'] is False
