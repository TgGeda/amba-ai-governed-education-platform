# AmbaAI production RAG layer

This package adds semantic/heading-aware chunking, metadata filters, vector + BM25 hybrid retrieval, reciprocal-rank fusion, reranking, structured context assembly, source citations, confidence gating, and source version control.

## Integration points

1. In your ingestion worker, register the document version with `SourceControl`, extract page text, call `SemanticChunker.chunk`, embed the resulting chunks, and persist each chunk plus metadata.
2. Adapt your current vector store to the `vector_search(query, k, filters)` callable signature.
3. Wrap the existing Ollama/local model call as `llm_generate(prompt) -> str`.
4. Build `ProductionRAGPipeline` once in Tutor service and call `answer(RetrievalQuery(...))`.
5. Render `GroundedAnswer.citations` and confidence in Tutor UI.

This implementation is local/offline and does not use AWS.
