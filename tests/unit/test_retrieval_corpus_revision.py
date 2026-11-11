from __future__ import annotations

from amba_ai.rag.corpus_revision import RetrievalCorpusCache, RetrievalCorpusRevision


def revision(*, documents: str = "d", chunks: str = "c", governance: str = "g") -> RetrievalCorpusRevision:
    return RetrievalCorpusRevision(documents, chunks, governance)


def test_revision_changes_for_each_governed_corpus_dimension() -> None:
    baseline = revision()
    assert baseline.revision_id != revision(documents="changed").revision_id
    assert baseline.revision_id != revision(chunks="changed").revision_id
    assert baseline.revision_id != revision(governance="changed").revision_id


def test_cache_is_instance_owned_and_revision_keyed() -> None:
    first = RetrievalCorpusCache()
    second = RetrievalCorpusCache()
    value = object()
    first._revision_id = revision().revision_id
    first._result = value
    assert first.get(revision()) is value
    assert second.get(revision()) is None
    first.invalidate()
    assert first.get(revision()) is None
