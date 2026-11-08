from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def test_generator_is_deterministic_and_score_withheld():
 cmd=[sys.executable,str(ROOT/'tools/readiness/generate_readiness_reflection.py')];subprocess.run(cmd,check=True,cwd=ROOT);a=(ROOT/'submission/artifacts/readiness_reflection.json').read_bytes();subprocess.run(cmd,check=True,cwd=ROOT);b=(ROOT/'submission/artifacts/readiness_reflection.json').read_bytes();assert a==b
 p=json.loads(a);assert p['overall_project_score'] is None;assert p['score_status']=='withheld_pending_methodology_and_evidence_coverage';assert len(p['findings'])==19;assert p['y3172_mapping']['formal_y3172_conformance'] is False
