from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from amba_ai.readiness.assessment_service import ReadinessAssessmentService
from amba_ai.readiness.report_generator import write_reports
def main():
 reflection=ReadinessAssessmentService().assess(artifact_path=ROOT/'submission/artifacts/four_stage_evidence_chain.json',mapping_path=ROOT/'config/readiness_evidence_mapping.yaml',passage_catalog_path=ROOT/'kb/passages/verified_passage_catalog.json',y3172_records_path=ROOT/'kb/records/itu_y3172_verified_records.yaml',repository_root=ROOT)
 out=ROOT/'submission/artifacts';digest=write_reports(reflection,out/'readiness_reflection.json',out/'readiness_reflection_pretty.json',out/'readiness_reflection.md');print(f'finding_count={len(reflection.findings)}');print(f'overall_project_score=None');print('score_status=withheld_pending_methodology_and_evidence_coverage');print(f'sha256={digest}')
if __name__=='__main__':main()
