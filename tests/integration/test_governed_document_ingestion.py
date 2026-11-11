from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from amba_ai.db.database import Database
from amba_ai.exceptions import IngestionError
from amba_ai.governance.runtime.models import ChunkGovernanceDecision, Decision, IngestionDecision
from amba_ai.models.schemas import IngestedDocument
from amba_ai.services.governed_ingestion_service import GovernedIngestionService


class Repository:
    def __init__(self): self.documents={}; self.decisions={}; self.receipts=[]
    def get_document(self, document_id): return self.documents.get(document_id)
    def receipt(self,event_type,payload,document_id=None,operation=None): self.receipts.append((event_type,payload)); return "EDU-GOV-INGEST"
    def delete_document_records(self, document_id): self.documents.pop(document_id,None); self.decisions.pop(document_id,None)


class Governance:
    def __init__(self,path): self.repository=Repository(); self.path=path
    def preflight_file(self,path): return hashlib.sha256(Path(path).read_bytes()).hexdigest(),()
    def assess_ingestion(self,path,text):
        digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return IngestionDecision(Decision.RESTRICTED,digest,(),("index_document",),(),(),True,True,"ASSESS")
    def record_document(self,document_id,decision): self.repository.documents[document_id]={"source_sha256":decision.source_sha256}
    def assess_chunks(self,document_id,chunks):
        out=[]
        for row in chunks:
            blocked="FINAL EXAM ANSWER KEY" in row["text"]
            out.append(ChunkGovernanceDecision(int(row["id"]),document_id,hashlib.sha256(row["text"].encode()).hexdigest(),Decision.REVIEW if blocked else Decision.RESTRICTED,"untrusted_source",not blocked,not blocked,("index_document",) if not blocked else (),(),(),"pending_review" if blocked else "approved"))
        self.repository.decisions[document_id]=out
        return tuple(out)


class Engine:
    def __init__(self): self.ids=set(); self.docs=set(); self.corpus_cache=SimpleNamespace(invalidate=lambda:None); self.fail=False
    def index_document(self,document_id,*,permitted_chunk_ids):
        if self.fail: raise RuntimeError("index failed")
        self.ids.update(permitted_chunk_ids); self.docs.add(document_id)
    def indexed_chunk_ids(self): return frozenset(self.ids)
    def has_document(self,document_id): return document_id in self.docs
    def remove_document(self,document_id): self.docs.discard(document_id); self.ids.clear()


def chunker(*,document_id,text):
    parts=[part.strip() for part in text.split("\n\n") if part.strip()]
    return [SimpleNamespace(text=value,chunk_index=index,source_ref="lesson") for index,value in enumerate(parts)]


def service(tmp_path,engine=None,extractor=None):
    source=tmp_path/"lesson.txt"; source.write_text("Fractions are parts of a whole.\n\nFINAL EXAM ANSWER KEY",encoding="utf-8")
    db=Database(tmp_path/"app.db"); governance=Governance(source); engine=engine or Engine()
    def default_extract(path,whisper_model): return IngestedDocument("Lesson",str(path),"text",Path(path).read_text(),{})
    return source,db,governance,engine,GovernedIngestionService(db=db,rag_engine=engine,runtime_governance=governance,extractor=extractor or default_extract,chunker=chunker)


def test_governed_ingestion_indexes_only_approved_chunks_and_emits_receipt(tmp_path):
    source,db,gov,engine,svc=service(tmp_path)
    result=svc.ingest(source)
    chunks=db.get_chunks(result.document_id)
    assert len(chunks)==2
    assert engine.indexed_chunk_ids()==frozenset({int(chunks[0]["id"])})
    assert result.metadata["ingestion_status"]=="complete"
    assert result.metadata["ingestion_receipt_id"]=="EDU-GOV-INGEST"
    assert gov.repository.get_document(result.document_id) is not None


def test_index_failure_leaves_document_unindexed_and_removes_primary_record(tmp_path):
    engine=Engine(); engine.fail=True
    source,db,gov,_engine,svc=service(tmp_path,engine=engine)
    with pytest.raises(IngestionError,match="failed closed"):
        svc.ingest(source)
    assert db.list_documents()==[]
    assert engine.indexed_chunk_ids()==frozenset()
    assert gov.repository.documents=={}


def test_changed_digest_fails_before_primary_persistence(tmp_path):
    def changed_extract(path,whisper_model):
        material=Path(path).read_text(); Path(path).write_text(material+" changed",encoding="utf-8")
        return IngestedDocument("Lesson",str(path),"text",material,{})
    source,db,_gov,engine,svc=service(tmp_path,extractor=changed_extract)
    with pytest.raises(IngestionError,match="digest changed"):
        svc.ingest(source)
    assert db.list_documents()==[]
    assert engine.indexed_chunk_ids()==frozenset()

def test_chunker_receives_positive_allocated_document_id(tmp_path):
    observed_document_ids=[]
    def strict_chunker(*,document_id,text):
        from amba_ai.models.schemas import TextChunk
        observed_document_ids.append(document_id)
        return [TextChunk(doc_id=document_id,chunk_index=0,text=text,source_ref="lesson")]
    source,db,governance,engine,_svc=service(tmp_path)
    source.write_text(
        "Fractions represent equal parts of a whole.",
        encoding="utf-8",
    )
    governance.path=source
    svc=GovernedIngestionService(
        db=db,
        rag_engine=engine,
        runtime_governance=governance,
        extractor=lambda path,whisper_model: IngestedDocument("Lesson",str(path),"text",Path(path).read_text(),{}),
        chunker=strict_chunker,
    )
    result=svc.ingest(source)
    assert result.document_id > 0
    assert observed_document_ids == [result.document_id]
    chunks=db.get_chunks(result.document_id)
    assert chunks
    assert all(int(row["document_id"]) == result.document_id for row in chunks)
    assert all(int(row["document_id"]) > 0 for row in chunks)


def test_chunk_construction_failure_rolls_back_document_transaction(tmp_path):
    def failing_chunker(*,document_id,text):
        raise ValueError("synthetic chunk failure")
    source,db,governance,engine,_svc=service(tmp_path)
    svc=GovernedIngestionService(
        db=db,
        rag_engine=engine,
        runtime_governance=governance,
        extractor=lambda path,whisper_model: IngestedDocument("Lesson",str(path),"text",Path(path).read_text(),{}),
        chunker=failing_chunker,
    )
    with pytest.raises(IngestionError,match="failed closed"):
        svc.ingest(source)
    assert db.list_documents() == []
    assert engine.indexed_chunk_ids() == frozenset()
    assert governance.repository.documents == {}

def test_chunk_draft_without_document_id_is_bound_to_allocated_document(tmp_path):
    source,db,governance,engine,svc=service(tmp_path)
    result=svc.ingest(source)
    chunks=db.get_chunks(result.document_id)
    assert len(chunks) == 2
    assert all(int(row["document_id"]) == result.document_id for row in chunks)


def test_explicit_mismatched_chunk_document_id_rolls_back(tmp_path):
    from amba_ai.models.schemas import TextChunk
    def mismatched_chunker(*,document_id,text):
        return [TextChunk(doc_id=document_id + 1,chunk_index=0,text=text)]
    source,db,governance,engine,_svc=service(tmp_path)
    svc=GovernedIngestionService(
        db=db,
        rag_engine=engine,
        runtime_governance=governance,
        extractor=lambda path,whisper_model: IngestedDocument("Lesson",str(path),"text",Path(path).read_text(),{}),
        chunker=mismatched_chunker,
    )
    with pytest.raises(IngestionError,match="failed closed"):
        svc.ingest(source)
    assert db.list_documents() == []
    assert engine.indexed_chunk_ids() == frozenset()

