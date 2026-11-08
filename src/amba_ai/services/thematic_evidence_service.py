from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, yaml
from amba_ai.governance.thematic_evidence import EvidenceGap, ThematicEvidenceView

@dataclass(frozen=True,slots=True)
class ThematicEvidenceRunContext:
    stage_id:str
    views:tuple[ThematicEvidenceView,...]
    gaps:tuple[EvidenceGap,...]
    @property
    def passage_ids(self)->tuple[str,...]: return tuple(sorted({p for v in self.views for p in v.supporting_passage_ids}))
    @property
    def theme_ids(self)->tuple[str,...]: return tuple(v.theme_id for v in self.views)
    @property
    def gap_ids(self)->tuple[str,...]: return tuple(g.gap_id for g in self.gaps)
    def to_dict(self)->dict[str,Any]: return {'stage_id':self.stage_id,'verified_passage_ids':list(self.passage_ids),'thematic_views':[v.to_dict() for v in self.views],'evidence_gaps':[g.to_dict() for g in self.gaps],'binding_finding_eligible':False}

class ThematicEvidenceService:
    def __init__(self,*,records_root:Path,gaps_path:Path,routing_path:Path):
        self._views={}; self._gaps={}
        for path in sorted(records_root.glob('*thematic_evidence_views.json')):
            for raw in json.loads(path.read_text(encoding='utf-8'))['views']:
                self._views[raw['theme_id']]=ThematicEvidenceView(theme_id=raw['theme_id'],theme=raw['theme'],source_id=raw['source_id'],supporting_passage_ids=tuple(raw['supporting_passage_ids']),evidence_status=raw['evidence_status'],gap_ids=tuple(raw['gap_ids']),source_citation_eligible=raw['source_citation_eligible'],contextual_evidence_eligible=raw['contextual_evidence_eligible'],provision_citation_eligible=raw['provision_citation_eligible'],binding_finding_eligible=raw['binding_finding_eligible'],historical_qualification_required=raw.get('historical_qualification_required',False),current_after_2024_25=raw.get('current_after_2024_25'),verified_successor_identified=raw.get('verified_successor_identified'))
        for raw in yaml.safe_load(gaps_path.read_text(encoding='utf-8')).get('gaps',[]): self._gaps[raw['gap_id']]=EvidenceGap(**raw)
        self._routing=yaml.safe_load(routing_path.read_text(encoding='utf-8'))['stages']
    def for_stage(self,stage_id:str)->ThematicEvidenceRunContext:
        ids=tuple(self._routing.get(stage_id,()))
        missing=[x for x in ids if x not in self._views]
        if missing: raise ValueError(f'unknown thematic view ids for {stage_id}: {missing}')
        views=tuple(self._views[x] for x in ids)
        gaps=tuple(self._gaps[g] for v in views for g in v.gap_ids)
        if any(v.binding_finding_eligible for v in views): raise ValueError('thematic views cannot activate binding findings')
        return ThematicEvidenceRunContext(stage_id,views,gaps)
