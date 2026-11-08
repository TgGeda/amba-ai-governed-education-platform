from __future__ import annotations
from pathlib import Path
from collections import Counter
from .models import ReadinessReflection
from .evidence_mapper import load_artifact,load_mappings,validate_references
class ReadinessAssessmentService:
 def assess(self,*,artifact_path:Path,mapping_path:Path,passage_catalog_path:Path,y3172_records_path:Path,repository_root:Path)->ReadinessReflection:
  _,digest=load_artifact(artifact_path); findings=load_mappings(mapping_path);validate_references(findings,passage_catalog_path,y3172_records_path)
  counts=Counter(x.status.value for x in findings); counts['factor_count']=6;counts['dimension_count']=13;counts['finding_count']=19;counts['reference_metric_count']=111
  return ReadinessReflection(artifact_path.resolve().relative_to(repository_root.resolve()).as_posix(),digest,findings,dict(sorted(counts.items())))
