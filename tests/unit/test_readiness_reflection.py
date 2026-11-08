from pathlib import Path
from amba_ai.readiness.evidence_mapper import load_mappings
ROOT=Path(__file__).resolve().parents[2]
def test_mapping_preserves_complete_framework():
 f=load_mappings(ROOT/'config/readiness_evidence_mapping.yaml');assert len(f)==19;assert len([x for x in f if x.framework_element_type=='factor'])==6;assert len([x for x in f if x.framework_element_type=='dimension'])==13
def test_allowed_statuses_only(): assert {x.status.value for x in load_mappings(ROOT/'config/readiness_evidence_mapping.yaml')} <= {'demonstrated','partially_demonstrated','not_demonstrated','not_applicable','insufficient_evidence','unresolved','not_assessed'}
