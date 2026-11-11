from __future__ import annotations
import json
from types import MappingProxyType
import pytest
from amba_ai.governance.runtime.output_guardrails import OutputDisposition,digest_material,sanitize_structure
from amba_ai.services.governed_result_delivery import GovernedResultDeliveryService,GovernedResultEnvelope
from amba_ai.services.result_sinks import DEFAULT_SINKS,GovernedDeliveryError
RAW=("learner@example.com","Student ID: ABC-123",r"F:\Private\student_record.txt")
def envelope():
 raw={"answer_text":r"Contact learner@example.com. Student ID: ABC-123. File F:\Private\student_record.txt","metadata":{}}
 sanitized,_=sanitize_structure(raw)
 return GovernedResultEnvelope("EDU-OUT-1","learning.tutor.answer",7,dict(sanitized),digest_material(sanitized),OutputDisposition.REDACT_AND_DISPLAY,"EDU-TRACE-1","EDU-AUDIT-1")
class DB:
 def __init__(self):self.values=[]
 def log_chat(self,*a,**k):self.values.append((a,k))
 def insert_summary(self,*a,**k):self.values.append((a,k));return 1
 def insert_flashcards(self,*a,**k):self.values.append((a,k))
 def insert_mcqs(self,*a,**k):self.values.append((a,k))
class Memory:
 def __init__(self):self.values=[]
 def save_exchange(self,**k):self.values.append(k)
def test_all_sinks_accept_only_verified_sanitized_envelopes(tmp_path):
 e=envelope(); svc=GovernedResultDeliveryService();db=DB();mem=Memory();clipboard=[];audit=[]
 contexts={"tutor_display":{},"summary_persistence":{"db":db},"notes_persistence":{"db":db},"study_assets_persistence":{"db":db},"chat_log":{"db":db,"user_text":"safe learner prompt"},"learning_memory":{"memory":mem,"user_text":"safe learner prompt","session_id":"s"},"export":{"path":tmp_path/"out.txt"},"clipboard":{"writer":clipboard.append},"audit":{"writer":audit.append}}
 # Use operation-appropriate envelopes for structured sinks.
 summary_material={"markdown_notes":e.sanitized_material["answer_text"],"model_name":"m","metadata":{}}
 summary=GovernedResultEnvelope(e.output_id,"learning.summary.generate",7,summary_material,digest_material(summary_material),e.disposition,e.trace_id,e.audit_receipt)
 assets_material={"flashcards":[],"mcqs":[],"metadata":{}}
 assets=GovernedResultEnvelope(e.output_id,"learning.flashcards.generate",7,assets_material,digest_material(assets_material),e.disposition,e.trace_id,e.audit_receipt)
 for name in DEFAULT_SINKS:
  chosen=summary if name in {"summary_persistence","notes_persistence"} else assets if name=="study_assets_persistence" else e
  svc.deliver(chosen,name,**contexts[name])
 combined=repr(db.values)+repr(mem.values)+repr(clipboard)+repr(audit)+(tmp_path/"out.txt").read_text()
 for secret in RAW:assert secret not in combined
@pytest.mark.parametrize("sink_name",sorted(DEFAULT_SINKS))
def test_no_sink_accepts_raw_model_response(sink_name):
 with pytest.raises(TypeError):DEFAULT_SINKS[sink_name].deliver("raw model response")
def test_tampered_envelope_is_rejected():
 e=envelope();object.__setattr__(e,"sanitized_material",MappingProxyType({"answer_text":"tampered"}))
 with pytest.raises(GovernedDeliveryError):GovernedResultDeliveryService().deliver(e,"tutor_display")
