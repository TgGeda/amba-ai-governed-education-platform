from __future__ import annotations
from types import SimpleNamespace
from typing import Any
from amba_ai.services.job_governance import JobGovernanceCoordinator
from amba_ai.services.job_service import JobService
from amba_ai.models.schemas import AnswerResult
from amba_ai.services.governed_result_delivery import GovernedResultDeliveryService

class Completion:
    def require_delivery_acknowledged(self): pass
class Coordinator(JobGovernanceCoordinator):
    def __init__(self): self.completed_material=None
    def begin(self,*,method_name,input_metadata,context): return SimpleNamespace(method_name=method_name)
    def complete(self,*,invocation,result_material,result_metadata):
        self.completed_material=dict(result_material); return Completion()
class Validation:
    def __init__(self, material):
        from amba_ai.governance.runtime.output_guardrails import OutputDisposition, digest_material
        self.output_id = "EDU-OUT-TEST"
        self.document_id = 1
        self.operation = "tutor_answer"
        self.disposition = OutputDisposition.REDACT_AND_DISPLAY
        self.sanitized_material = material
        self.sanitized_output_sha256 = digest_material(material)
        self.trace_id = "EDU-TRACE-TEST"
        self.audit_receipt = "EDU-AUDIT-TEST"
    def evidence(self): return {'decision':'redact_and_display'}
class RuntimeGovernance:
    def authorize_generation(self,*args,**kwargs): pass
    def filter_retrieval(self,document_id,operation,hits):
        return SimpleNamespace(
            hits=tuple(hits),
            excluded_chunk_ids=(),
            applied_controls=("governed_retrieval",),
            evidence_ids=(),
            gaps=(),
            governance_receipt_id="EDU-GOV-TEST",
        )
    def validate_output(self,*args,**kwargs):
        material=dict(args[2]); material['answer_text']='safe answer'; return Validation(material)
class Model:
    def get_client_for_task(self,task): return SimpleNamespace()
    def generate_stream(self,**kwargs): yield 'unsafe'; yield ' answer'
class Memory:
    def __init__(self): self.saved=[]
    def get_relevant_history_text(self,*args,**kwargs): return ''
    def save_exchange(self,**kwargs): self.saved.append(dict(kwargs))
class Tracker:
    def set_active_tab(self,value): pass
    def set_active_document(self,**kwargs): pass
    def set_due_flashcards(self,value): pass
    def generate_system_prompt(self): return ''
class DB:
    path=None
    def __init__(self): self.logs=[]
    def log_chat(self,*args,**kwargs): self.logs.append(args)
class RAG:
    index=SimpleNamespace(ntotal=1)
    def search(self,question,top_k): return []
class GovernedRetrieval:
    def retrieve(self,question,*,document_id,operation,top_k):
        return SimpleNamespace(document_id=document_id,operation=operation,hits=(SimpleNamespace(chunk_id=1,text='evidence',source_ref='lesson'),),retrieved_chunk_ids=(1,),excluded_chunk_ids=(),receipt_id='EDU-GOV-RETRIEVE',corpus_revision_id='REV-1')
class GroundedAnswer:
    def generate(self,question,retrieval,*,max_tokens,relevant_memory):
        return AnswerResult(answer_text='unsafe answer',sources=['lesson'],model_name='test-model',metadata={'candidate':True,'delivery_authorized':False})
class Service(JobService):
    def _begin_job_governance(self,**kwargs):
        return self.governance_coordinator.begin(method_name=kwargs['method_name'],input_metadata=kwargs['input_metadata'],context=kwargs['governance_context'])

def service():
    c=Coordinator(); db=DB(); memory=Memory()
    s=Service(db=db,rag_engine=RAG(),memory_manager=memory,context_tracker=Tracker(),model_service=Model(),llm_client=SimpleNamespace(),governance_coordinator=c,runtime_governance=RuntimeGovernance(),governed_retrieval_service=GovernedRetrieval(),grounded_answer_service=GroundedAnswer(),governed_result_delivery=GovernedResultDeliveryService())
    return s,c,db,memory

def test_coordinator_receives_sanitized_material():
    s,c,_,_=service()
    result=s._complete_job_governance(invocation=SimpleNamespace(method_name='tutor_answer'),result_material={'answer_text':'unsafe answer'},result_metadata={'document_id':1,'output_type':'answer_result'})
    assert result['answer_text']=='safe answer'; assert c.completed_material==result

def test_stream_persists_and_releases_only_sanitized_answer():
    s,c,db,memory=service()
    assert list(s.tutor_answer_stream('question',document_id=1,governance_context=object()))==['safe answer']
    assert db.logs[-1][1]=='safe answer'; assert memory.saved[-1]['assistant_text']=='safe answer'
    assert 'unsafe answer' not in repr(db.logs); assert 'unsafe answer' not in repr(memory.saved)
    assert c.completed_material['answer_text']=='safe answer'
