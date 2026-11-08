from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def test_plan_generation_is_deterministic_and_bound_to_readiness_artifact():
    cmd=[sys.executable,str(ROOT/'tools/readiness/generate_readiness_evidence_plan.py')];subprocess.run(cmd,check=True,cwd=ROOT);a=(ROOT/'submission/artifacts/readiness_evidence_plan.json').read_bytes();subprocess.run(cmd,check=True,cwd=ROOT);b=(ROOT/'submission/artifacts/readiness_evidence_plan.json').read_bytes();assert a==b
    plan=json.loads(a);readiness=(ROOT/plan['readiness_reflection_path']).read_bytes();assert hashlib.sha256(readiness).hexdigest()==plan['readiness_reflection_sha256'];assert plan['minimum_threshold_closure_plan']['selected_metrics']==['D11-M01','F5-M01'];assert plan['claim_boundaries']['project_score_guaranteed_after_plan'] is False
