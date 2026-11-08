from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from amba_ai.readiness.assessment_service import ReadinessAssessmentService
from amba_ai.readiness.report_generator import write_reports
from amba_ai.readiness.scoring_service import ReadinessScoringService

def main():
    reflection=ReadinessAssessmentService().assess(artifact_path=ROOT/'submission/artifacts/four_stage_evidence_chain.json',mapping_path=ROOT/'config/readiness_evidence_mapping.yaml',passage_catalog_path=ROOT/'kb/passages/verified_passage_catalog.json',y3172_records_path=ROOT/'kb/records/itu_y3172_verified_records.yaml',repository_root=ROOT)
    scoring=ReadinessScoringService().score(findings=reflection.to_dict()['findings'],metric_definitions_path=ROOT/'config/readiness_metric_definitions.yaml',methodology_path=ROOT/'config/readiness_scoring_methodology.yaml')
    out=ROOT/'submission/artifacts';digest=write_reports(reflection,out/'readiness_reflection.json',out/'readiness_reflection_pretty.json',out/'readiness_reflection.md',scoring)
    print(f'finding_count={len(reflection.findings)}');print(f"project_proxy_metric_count={scoring['implemented_project_proxy_metric_count']}");print(f"evidence_coverage={scoring['overall']['coverage']['coverage_ratio']}");print(f"overall_project_score={scoring['overall']['score']}");print(f"score_status={scoring['overall']['status']}");print(f'sha256={digest}')
if __name__=='__main__':main()
