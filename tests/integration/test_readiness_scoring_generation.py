from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def test_scoring_output_is_deterministic_and_fail_closed():
 cmd=[sys.executable,str(ROOT/'tools/readiness/generate_readiness_reflection.py')];subprocess.run(cmd,check=True,cwd=ROOT);a=(ROOT/'submission/artifacts/readiness_reflection.json').read_bytes();subprocess.run(cmd,check=True,cwd=ROOT);b=(ROOT/'submission/artifacts/readiness_reflection.json').read_bytes();assert a==b
 p=json.loads(a);assert p['overall_project_score'] is None;assert p['score_status']=='withheld_insufficient_evidence_coverage';assert p['evidence_coverage']['coverage_ratio']==0.736842;assert p['scoring']['implemented_project_proxy_metric_count']==19;assert p['scoring']['framework_metric_reference_count']==111;assert p['scoring']['claim_boundaries']['official_itu_score'] is False
