from __future__ import annotations
from types import SimpleNamespace
import pytest
from amba_ai.services.governed_retrieval_service import GovernedRetrievalService
from amba_ai.services.grounded_answer_service import GroundedAnswerService
from amba_ai.services.job_service import JobService
from amba_ai.rag.engine import FaissRAGEngine

class Repo:
 def receipt(self,*a,**k): return "EDU-GOV-RETRIEVE"
class Gov:
 def __init__(self): self.repository=Repo(); self.authorized=[]
 def authorize_generation(self,d,o): self.authorized.append((d,o))
 def filter_retrieval(self,d,o,h): return SimpleNamespace(hits=tuple(x for x in h if x.chunk_id==1),excluded_chunk_ids=(2,))
class Revision: revision_id="REV-1"
class Corpus:
 eligible_chunk_ids=frozenset({1});excluded_chunk_ids=frozenset({2});revision=Revision()
 def require_aligned(self): pass
class Builder:
 def build(self,operation): return Corpus()
class Engine:
 def search(self,q,top_k): return [SimpleNamespace(chunk_id=1,document_id=7,text="Fractions are equal parts.",source_ref="lesson",score=.9),SimpleNamespace(chunk_id=2,document_id=7,text="answer key",source_ref="private",score=.8)]
class Model:
 def __init__(self): self.calls=0
 def generate(self,*a,**k): self.calls+=1; return "Fractions divide a whole [SOURCE 1]."
class Formatter:
 def format_response(self,raw_llm_answer,retrieved_context): return SimpleNamespace(formatted_answer=raw_llm_answer,citations=["SOURCE 1"],is_low_confidence=False)

def test_governed_retrieval_filters_and_receipts():
 g=Gov(); value=GovernedRetrievalService(rag_engine=Engine(),runtime_governance=g,corpus_builder=Builder()).retrieve("fractions",document_id=7)
 assert value.retrieved_chunk_ids==(1,); assert value.excluded_chunk_ids==(2,); assert value.receipt_id=="EDU-GOV-RETRIEVE"

def test_grounded_answer_is_undelivered_candidate():
 g=Gov(); r=GovernedRetrievalService(rag_engine=Engine(),runtime_governance=g,corpus_builder=Builder()).retrieve("fractions",document_id=7)
 m=Model(); a=GroundedAnswerService(model_service=m,formatter=Formatter()).generate("fractions",r)
 assert m.calls==1; assert a.metadata["candidate"] is True; assert a.metadata["delivery_authorized"] is False; assert a.metadata["retrieval_receipt_id"]=="EDU-GOV-RETRIEVE"

def test_engine_has_no_answer_generation_surface():
 assert "answer" not in FaissRAGEngine.__dict__
