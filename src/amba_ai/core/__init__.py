from __future__ import annotations

from .agent_bridge import AgentBridge, AgentCommand
from .agent_orchestrator import AgentOrchestrator
from .bluetooth_service import BluetoothDevice, BluetoothService
from .content_delivery import (
    build_fast_summary,
    concepts_html,
    fill_missing_flashcards,
    md_to_html,
    normalize_card,
    normalize_mcq,
    outline_html,
    source_label,
)
from .context_tracker import ContextTracker, RuntimeContextSnapshot
from .crystallize import StudyPackCompiler, StudyPackResult
from .export import export_flashcards_csv, export_markdown, export_mcqs_csv, export_pdf
from .hybrid_router import HybridRouter, RouterInvocation, TaskCapability
from .ingest import ExtractionResult, IngestedDocument, detect_kind, ingest_path, persist_upload
from .learning_pack import (
    LearningPackArtifact,
    LearningPackResult,
    build_learning_bundle,
    compile_document_agnostic_bundle,
    create_quiz_pdf,
    create_study_card_png,
    create_study_guide_pdf,
    resolve_source,
)
from .memory_manager import MemoryManager, VectorInfiniteMemory
from .ocr_loader import WindowsOcrLoader
from .pedagogy import PedagogicalFormatter, PedagogicalResponse
from .preprocessing import chunk_text, chunk_text_dicts, normalize_text, split_paragraphs
from .rlhf_service import FeedbackEvent, FeedbackRecord, RLHFService
from .safety_service import SafetyDecision, SafetyService
from .study_tools import generate_flashcards, generate_mcqs
from .summarizer import ExtractiveSummaryResult, SummaryResult, extractive_summary, summarize_document_text
from .translation_service import TranslationResult, TranslationService

__all__ = [
    "AgentBridge",
    "AgentCommand",
    "AgentOrchestrator",
    "BluetoothDevice",
    "BluetoothService",
    "ContextTracker",
    "ExtractionResult",
    "ExtractiveSummaryResult",
    "FeedbackEvent",
    "FeedbackRecord",
    "HybridRouter",
    "IngestedDocument",
    "LearningPackArtifact",
    "LearningPackResult",
    "MemoryManager",
    "PedagogicalFormatter",
    "PedagogicalResponse",
    "RLHFService",
    "RouterInvocation",
    "RuntimeContextSnapshot",
    "SafetyDecision",
    "SafetyService",
    "StudyPackCompiler",
    "StudyPackResult",
    "SummaryResult",
    "TaskCapability",
    "TranslationResult",
    "TranslationService",
    "VectorInfiniteMemory",
    "WindowsOcrLoader",
    "build_fast_summary",
    "build_learning_bundle",
    "chunk_text",
    "chunk_text_dicts",
    "compile_document_agnostic_bundle",
    "concepts_html",
    "create_quiz_pdf",
    "create_study_card_png",
    "create_study_guide_pdf",
    "detect_kind",
    "export_flashcards_csv",
    "export_markdown",
    "export_mcqs_csv",
    "export_pdf",
    "extractive_summary",
    "fill_missing_flashcards",
    "generate_flashcards",
    "generate_mcqs",
    "ingest_path",
    "md_to_html",
    "normalize_card",
    "normalize_mcq",
    "normalize_text",
    "outline_html",
    "persist_upload",
    "resolve_source",
    "source_label",
    "split_paragraphs",
    "summarize_document_text",
]