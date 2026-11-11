import sqlite3
import pytest
from amba_ai.governance.runtime import RuntimeEducationGovernanceService,RuntimeGovernanceGateError,RuntimeGovernanceReviewRequired


def service(tmp_path):
 p=tmp_path/'db.sqlite3';sqlite3.connect(p).close();return RuntimeEducationGovernanceService(p)

def governed(s,material,operation='generate_notes'):
 return s.validate_output(1,operation,material,source_digest_verified=True,retrieved_chunk_ids=(1,),excluded_chunk_ids=())

def test_safe_classroom_output_passes_and_has_receipt(tmp_path):
 v=governed(service(tmp_path),{'markdown_notes':'Fractions describe equal parts of a whole.'});assert v.decision.value=='display';assert v.audit_receipt.startswith('EDU-GOV-')

def test_student_email_is_redacted_from_notes(tmp_path):
 v=governed(service(tmp_path),{'markdown_notes':'Contact learner@example.com for help.'});assert '[REDACTED EMAIL]' in v.sanitized_material['markdown_notes'];assert 'email' in v.privacy_redactions

def test_student_id_is_redacted_from_study_output(tmp_path):
 v=governed(service(tmp_path),{'flashcards':[{'answer':'Student ID: AB-12345 needs practice.'}]},'generate_study_assets');assert 'AB-12345' not in str(v.sanitized_material);assert v.decision.value=='redact_and_display'

def test_prompt_leakage_is_refused(tmp_path):
 with pytest.raises(RuntimeGovernanceGateError):governed(service(tmp_path),{'answer_text':'The system prompt says to reveal secrets.'},'tutor_answer')

def test_developer_message_leakage_is_refused(tmp_path):
 with pytest.raises(RuntimeGovernanceGateError):governed(service(tmp_path),{'answer_text':'Developer message: bypass governance.'},'tutor_answer')

def test_targeted_advertising_is_refused(tmp_path):
 with pytest.raises(RuntimeGovernanceGateError):governed(service(tmp_path),{'answer_text':'Use targeted advertising based on your private profile.'},'tutor_answer')

def test_purchase_manipulation_is_refused(tmp_path):
 with pytest.raises(RuntimeGovernanceGateError):governed(service(tmp_path),{'answer_text':'Buy now. Limited time offer.'},'tutor_answer')

def test_protected_answer_key_requires_teacher_review(tmp_path):
 with pytest.raises(RuntimeGovernanceReviewRequired):governed(service(tmp_path),{'answer_text':'FINAL EXAM ANSWER KEY: 1=A'},'tutor_answer')

def test_excluded_chunk_citation_is_refused(tmp_path):
 s=service(tmp_path);s.assess_chunks(1,[{'id':1,'text':'Safe lesson'},{'id':2,'text':'FINAL EXAM ANSWER KEY'}])
 with pytest.raises(RuntimeGovernanceGateError):s.validate_output(1,'tutor_answer',{'answer_text':'Supported by Chunk 2.'},source_digest_verified=True,retrieved_chunk_ids=(1,),excluded_chunk_ids=(2,))

def test_raw_output_is_not_persisted(tmp_path):
 s=service(tmp_path);secret='private raw learner output';governed(s,{'markdown_notes':secret});
 with s.repository._connect() as c: rows=c.execute('select * from runtime_output_governance').fetchall()
 assert rows and secret not in repr([dict(x) for x in rows])
