from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import json, unicodedata, yaml

REVIEW_ID="AMBA-GOV-ACADEMIC-REVIEW-001"
SUFFICIENT="sufficient_for_defined_context"
INSUFFICIENT="insufficient_evidence"
class ThematicEvidenceError(ValueError): pass

def canonicalize(text:str)->str:
    text=unicodedata.normalize("NFC",text.replace("\r\n","\n").replace("\r","\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()

@dataclass(frozen=True,slots=True)
class ThematicEvidenceDefinition:
    theme_id:str; theme:str; source_id:str; supporting_passage_ids:tuple[str,...]
    historical_qualification_required:bool=False
    current_after_2024_25:bool|None=None
    verified_successor_identified:bool|None=None

@dataclass(frozen=True,slots=True)
class EvidenceGap:
    gap_id:str; gap_type:str; subject:str; source_id:str; evidence_status:str
    disposition:str; recommended_action:str; reportable:bool=True
    def to_dict(self)->dict[str,Any]: return {k:getattr(self,k) for k in self.__dataclass_fields__}

@dataclass(frozen=True,slots=True)
class ThematicEvidenceView:
    theme_id:str; theme:str; source_id:str; supporting_passage_ids:tuple[str,...]
    evidence_status:str; gap_ids:tuple[str,...]
    source_citation_eligible:bool; contextual_evidence_eligible:bool
    provision_citation_eligible:bool; binding_finding_eligible:bool
    historical_qualification_required:bool=False
    current_after_2024_25:bool|None=None
    verified_successor_identified:bool|None=None
    def to_dict(self)->dict[str,Any]:
        return {k:(list(v) if isinstance(v,tuple) else v) for k,v in ((n,getattr(self,n)) for n in self.__dataclass_fields__)}

class VerifiedPassageCatalog:
    def __init__(self, passages:Mapping[str,Mapping[str,Any]]): self._passages=MappingProxyType(dict(passages))
    @classmethod
    def from_file(cls,path:Path)->"VerifiedPassageCatalog":
        payload=json.loads(path.read_text(encoding="utf-8")); rows=payload.get("passages",[])
        by_id={str(r["passage_id"]):r for r in rows}
        if len(by_id)!=len(rows): raise ThematicEvidenceError("duplicate passage_id")
        return cls(by_id)
    def require(self,passage_id:str,source_id:str)->Mapping[str,Any]:
        try: row=self._passages[passage_id]
        except KeyError as exc: raise ThematicEvidenceError(f"missing passage: {passage_id}") from exc
        if row.get("source_id")!=source_id: raise ThematicEvidenceError(f"source substitution: {passage_id}")
        if row.get("human_review_status")!="approved" or row.get("approval_record_id")!=REVIEW_ID: raise ThematicEvidenceError(f"unapproved passage: {passage_id}")
        if row.get("locator_verification_status") not in {"verified_exact","verified_structural"}: raise ThematicEvidenceError(f"unverified locator: {passage_id}")
        excerpt=canonicalize(str(row.get("exact_source_excerpt","")))
        if sha256(excerpt.encode()).hexdigest()!=row.get("exact_source_excerpt_sha256"): raise ThematicEvidenceError(f"excerpt hash mismatch: {passage_id}")
        if not all(row.get(k) is True for k in ("source_citation_eligible","contextual_evidence_eligible","provision_citation_eligible")): raise ThematicEvidenceError(f"citation-ineligible passage: {passage_id}")
        if row.get("binding_finding_eligible") is not False: raise ThematicEvidenceError(f"unexpected binding activation: {passage_id}")
        return row

class ThematicEvidenceResolver:
    def __init__(self,catalog:VerifiedPassageCatalog): self.catalog=catalog
    def resolve(self,definition:ThematicEvidenceDefinition)->tuple[ThematicEvidenceView,tuple[EvidenceGap,...]]:
        if not definition.supporting_passage_ids:
            gap=EvidenceGap(f"GAP-{definition.theme_id}","missing_verified_passage",definition.theme,definition.source_id,INSUFFICIENT,"unresolved","Verify and register an exact approved source passage before citation-bearing use.")
            view=ThematicEvidenceView(definition.theme_id,definition.theme,definition.source_id,(),INSUFFICIENT,(gap.gap_id,),False,False,False,False,definition.historical_qualification_required,definition.current_after_2024_25,definition.verified_successor_identified)
            return view,(gap,)
        for pid in definition.supporting_passage_ids: self.catalog.require(pid,definition.source_id)
        view=ThematicEvidenceView(definition.theme_id,definition.theme,definition.source_id,definition.supporting_passage_ids,SUFFICIENT,(),True,True,True,False,definition.historical_qualification_required,definition.current_after_2024_25,definition.verified_successor_identified)
        return view,()

def load_definitions(path:Path)->tuple[ThematicEvidenceDefinition,...]:
    payload=yaml.safe_load(path.read_text(encoding="utf-8")); source_id=str(payload["source_id"]); defaults=payload.get("defaults",{})
    return tuple(ThematicEvidenceDefinition(theme_id=str(x["theme_id"]),theme=str(x["theme"]),source_id=source_id,supporting_passage_ids=tuple(x.get("supporting_passage_ids",())),historical_qualification_required=bool(defaults.get("historical_qualification_required",False)),current_after_2024_25=defaults.get("current_after_2024_25"),verified_successor_identified=defaults.get("verified_successor_identified")) for x in payload["themes"])
