from hashlib import sha256
from pathlib import Path
import json
from amba_ai.application.evidence_chain_report import canonical_json,write_evidence_chain_report

def test_tampering_changes_artifact_digest(tmp_path:Path):
    payload={'schema_version':'1.0.0','stages':[{'stage_id':'STAGE-1','verified_evidence':['P-1']}]}
    path=tmp_path/'artifact.json'; digest=write_evidence_chain_report(payload,path)
    tampered=json.loads(path.read_text(encoding='utf-8')); tampered['stages'][0]['verified_evidence']=['SUBSTITUTED']
    assert sha256((canonical_json(tampered)+'\n').encode()).hexdigest()!=digest
