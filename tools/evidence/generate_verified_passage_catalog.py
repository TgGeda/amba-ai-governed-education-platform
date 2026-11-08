from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BATCH_FILES=(
 ROOT/"kb/passages/itu_y3172_verified_passages.jsonl",
 ROOT/"kb/passages/itu_ai_readiness_verified_passages.jsonl",
 ROOT/"kb/passages/unesco_ai_ethics_verified_passages.jsonl",
 ROOT/"kb/passages/unicef_ai_children_verified_passages.jsonl",
 ROOT/"kb/passages/ethiopian_cybersecurity_policy_verified_passages.jsonl",
 ROOT/"kb/passages/ethiopian_esdp_vi_verified_passages.jsonl",
 ROOT/"kb/passages/ethiopian_stme_verified_passages.jsonl",
 ROOT/"kb/passages/ethiopian_eca_qos_verified_passages.jsonl",
 ROOT/"kb/passages/ethiopian_pdpa_verified_passages.jsonl",
)
OUTPUT=ROOT/"kb/passages/verified_passage_catalog.json"

def canonicalize(text):
    text=unicodedata.normalize("NFC",text.replace("\r\n","\n").replace("\r","\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()

def main():
    passages=[]
    for path in BATCH_FILES:
        if not path.is_file(): raise FileNotFoundError(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip(): passages.append(json.loads(line))
    for p in passages:
        p["exact_source_excerpt"]=canonicalize(p["exact_source_excerpt"])
        p["exact_source_excerpt_sha256"]=hashlib.sha256(p["exact_source_excerpt"].encode()).hexdigest()
        p["source_citation_eligible"]=True
        p["provision_citation_eligible"]=(p.get("human_review_status")=="approved" and p.get("locator_verification_status") in {"verified_exact","verified_structural"} and p.get("excerpt_verification_status")=="verified_exact")
        p["binding_finding_eligible"]=False
    ids=[p["passage_id"] for p in passages]
    sources=sorted({p["source_id"] for p in passages})
    if len(passages)!=90 or len(ids)!=len(set(ids)) or len(sources)!=9:
        raise RuntimeError("expected 90 unique passages across nine sources")
    payload={"schema_version":"1.1.0","catalog_id":"AMBA-GOV-VERIFIED-PASSAGE-CATALOG","source_count":9,"passage_count":90,"catalog_status":"human_approved_for_defined_scope","academic_review_records":[{'review_record_id': 'AMBA-GOV-ACADEMIC-REVIEW-001', 'review_type': 'academic_advisor_review', 'review_status': 'approved', 'record_status': 'active', 'reviewer_name': 'Asrat Mulatu', 'reviewer_title': 'Professor', 'reviewer_role': 'Academic Advisor', 'reviewer_institution': 'Addis Ababa Science and Technology University', 'reviewer_institution_abbreviation': 'AASTU', 'relationship_to_project': 'Academic advisor to Birhan Abuhay Jemere', 'approval_method': 'active_shared_document_review', 'approved_passage_count': 90, 'record_owner': 'Birhan Abuhay Jemere', 'evidence': {'type': 'active_shared_document', 'reviewer_edits_present': True, 'reviewer_identity_visible_in_version_history': True, 'version_history_retained_externally': True, 'version_history_location': 'Microsoft 365 shared document', 'email_confirmation_available': True}, 'scope_boundary': 'Academic advisor approval supports catalog inclusion, citation within recorded boundaries, contextual analysis, and project documentation. It does not constitute AASTU institutional approval, a formal legal opinion, or automatic project-specific legal applicability.'}],"review_policy":{"source_citation_rule":"Every hash-verified document can be cited as a source.","provision_citation_rule":"Only human-approved verified passages can be cited as provisions.","binding_finding_rule":"Only binding, applicable, reviewed and activated provisions can support binding findings.","automated_extraction_can_self_approve":False},"review_summary":{"pending":sum(p.get("human_review_status")=="pending" for p in passages),"approved":sum(p.get("human_review_status")=="approved" for p in passages),"rejected":sum(p.get("human_review_status")=="rejected" for p in passages),"provision_citation_eligible":sum(p["provision_citation_eligible"] for p in passages),"binding_finding_eligible":0},"sources":[{"source_id":s,"passage_count":sum(p["source_id"]==s for p in passages)} for s in sources],"passages":sorted(passages,key=lambda p:(p["source_id"],p["physical_pdf_page_start"],p["passage_id"]))}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"output={OUTPUT.relative_to(ROOT).as_posix()}")
    print("source_count=9"); print("passage_count=90")
    print(f"provision_citation_eligible_count={payload['review_summary']['provision_citation_eligible']}")
    print("binding_finding_eligible_count=0")
if __name__=="__main__": main()
