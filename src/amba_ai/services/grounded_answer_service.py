from __future__ import annotations
from typing import Any
from amba_ai.config import get_model_for_task
from amba_ai.core.pedagogy import PedagogicalFormatter
from amba_ai.models.schemas import AnswerResult
from amba_ai.services.governed_retrieval_service import GovernedRetrieval

class GroundedAnswerService:
    def __init__(self, *, model_service: Any, formatter: Any | None=None) -> None:
        self.model_service=model_service; self.formatter=formatter or PedagogicalFormatter()
    @staticmethod
    def _text(hit: Any) -> str: return str(hit.get("text") if isinstance(hit,dict) else getattr(hit,"text","") or "")
    @staticmethod
    def _source(hit: Any) -> str: return str(hit.get("source_ref") if isinstance(hit,dict) else getattr(hit,"source_ref",None) or "Local Study Material")
    def generate(self, question: str, retrieval: GovernedRetrieval, *, max_tokens: int=1200, relevant_memory: str="") -> AnswerResult:
        if not retrieval.hits: raise ValueError("Grounded answer requires governed retrieval evidence.")
        sections=[f"[SOURCE {i}: {self._source(h)}]\n{self._text(h)}" for i,h in enumerate(retrieval.hits,1)]
        context="\n\n".join(sections)
        prompt=f"Student question:\n{question.strip()}\n\nRetrieved study material:\n{context}"
        if relevant_memory: prompt += f"\n\nRelevant learning memory (personalization only):\n{relevant_memory}"
        prompt += "\n\nAnswer only from the retrieved study material. Cite [SOURCE n]. If evidence is insufficient, say so."
        raw=self.model_service.generate(prompt,system="You are AmbaAI Tutor. Use only governed retrieved evidence.",task="tutor_chat",max_tokens=max_tokens,temperature=0.15)
        formatted=self.formatter.format_response(raw_llm_answer=str(raw),retrieved_context=list(retrieval.hits))
        sources=list(dict.fromkeys(self._source(h) for h in retrieval.hits))
        return AnswerResult(answer_text=formatted.formatted_answer,sources=sources,model_name=get_model_for_task("tutor_chat"),metadata={"candidate":True,"delivery_authorized":False,"retrieval_receipt_id":retrieval.receipt_id,"retrieved_chunk_ids":list(retrieval.retrieved_chunk_ids),"excluded_chunk_ids":list(retrieval.excluded_chunk_ids),"corpus_revision_id":retrieval.corpus_revision_id,"citations":formatted.citations,"is_low_confidence":formatted.is_low_confidence})
