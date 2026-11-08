from pathlib import Path
import json
from amba_ai.submission.json_pointer import resolve_json_pointer
from amba_ai.submission.manifest_builder import build_manifest
ROOT=Path(__file__).resolve().parents[2]
def test_json_pointer_resolution():assert resolve_json_pointer({'a':{'b':[1,2]}},'/a/b/1')==2
def test_manifest_contains_required_boundaries_and_pending_gates():
 m=build_manifest(ROOT,ROOT/'config/submission_artifact_requirements.yaml').to_dict();assert m['claim_boundaries']['official_itu_score'] is False;assert 'metric:D11-M01' in m['pending_gates'];assert 'metric:F5-M01' in m['pending_gates'];assert len(m['entries'])==11
