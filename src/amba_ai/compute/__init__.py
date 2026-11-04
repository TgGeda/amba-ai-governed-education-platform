from __future__ import annotations

from .cloud_llm import CloudGenerationResult, CloudLLMProvider
from .edge_slm import GenerationResult, OllamaClient
from .edge_whisper import EdgeWhisperTranscriber, TranscriptionResult, TranscriptionSegment

__all__ = [
    "CloudGenerationResult",
    "CloudLLMProvider",
    "EdgeWhisperTranscriber",
    "GenerationResult",
    "OllamaClient",
    "TranscriptionResult",
    "TranscriptionSegment",
]