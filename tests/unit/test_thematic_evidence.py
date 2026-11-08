from pathlib import Path
import json, pytest
from amba_ai.governance.thematic_evidence import *
ROOT=Path(__file__).resolve().parents[2]
def test_resolved_theme_uses_registered_passage():
 c=VerifiedPassageCatalog.from_file(ROOT/'kb/passages/verified_passage_catalog.json'); r=ThematicEvidenceResolver(c)
 v,g=r.resolve(ThematicEvidenceDefinition('HUMAN-CONTROL','human control','UNICEF-AI-CHILDREN-3.0',('UNICEF-HUMAN-DECISION',)))
 assert v.evidence_status==SUFFICIENT and v.provision_citation_eligible and not v.binding_finding_eligible and not g
def test_missing_support_becomes_reportable_gap():
 c=VerifiedPassageCatalog.from_file(ROOT/'kb/passages/verified_passage_catalog.json'); v,g=ThematicEvidenceResolver(c).resolve(ThematicEvidenceDefinition('MISSING','missing','UNICEF-AI-CHILDREN-3.0',()))
 assert v.evidence_status==INSUFFICIENT and not v.source_citation_eligible and g[0].reportable
def test_source_substitution_fails_closed():
 c=VerifiedPassageCatalog.from_file(ROOT/'kb/passages/verified_passage_catalog.json')
 with pytest.raises(ThematicEvidenceError): c.require('UNICEF-HUMAN-DECISION','ETH-ESDP-VI-2021')
