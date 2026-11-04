# src/amba_ai/core/summarizer.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.text_rank import TextRankSummarizer

from amba_ai.config import OLLAMA_MODEL
from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.exceptions import ModelUnavailableError
from amba_ai.logger import logger


SummarizerName = Literal["lexrank", "lsa", "textrank"]


DEFAULT_EXTRACTIVE_SENTENCE_COUNT = 24
MAX_EXTRACTIVE_SENTENCE_COUNT = 80
MIN_TEXT_LENGTH_TO_SUMMARIZE = 120

DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "You are an offline academic note generator. "
    "Generate concise, faithful, exam-ready notes. "
    "Do not invent facts. Preserve source anchors when available."
)


@dataclass(frozen=True)
class ExtractiveSummaryResult:
    compressed_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SummaryResult:
    markdown_notes: str
    model_name: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _context(
    *,
    operation: str,
    model_name: str | None = None,
    text: str | None = None,
    prompt: str | None = None,
    sentence_count: int | None = None,
    summarizer_name: str | None = None,
    tokens_requested: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "operation": operation,
    }

    if model_name is not None:
        context["model_name"] = model_name

    if text is not None:
        context["text_length"] = len(text)

    if prompt is not None:
        context["prompt_length"] = len(prompt)

    if sentence_count is not None:
        context["sentence_count"] = sentence_count

    if summarizer_name is not None:
        context["summarizer_name"] = summarizer_name

    if tokens_requested is not None:
        context["tokens_requested"] = tokens_requested

    context.update(extra)
    return context


def _validate_text_for_summary(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Input text must be non-empty.")

    cleaned = text.strip()

    if len(cleaned) < MIN_TEXT_LENGTH_TO_SUMMARIZE:
        raise ValueError(
            f"Input text is too short to summarize. "
            f"Minimum length is {MIN_TEXT_LENGTH_TO_SUMMARIZE} characters."
        )

    return cleaned


def _validate_sentence_count(sentence_count: int) -> int:
    if not isinstance(sentence_count, int):
        raise ValueError("sentence_count must be an integer.")

    if sentence_count <= 0:
        raise ValueError("sentence_count must be greater than zero.")

    return min(sentence_count, MAX_EXTRACTIVE_SENTENCE_COUNT)


def _get_sumy_summarizer(summarizer_name: SummarizerName):
    if summarizer_name == "lexrank":
        return LexRankSummarizer()

    if summarizer_name == "lsa":
        return LsaSummarizer()

    if summarizer_name == "textrank":
        return TextRankSummarizer()

    raise ValueError(
        f"Unsupported summarizer_name: {summarizer_name}. "
        "Expected one of: lexrank, lsa, textrank."
    )


def _extract_source_anchors(text: str, max_anchors: int = 40) -> list[str]:
    """
    Extract visible source anchors from text.

    Supports examples such as:
    - [Page 1]
    - [Slide 3]
    - chunk:0
    - chunk:12
    """
    patterns = [
        r"\[Page\s+\d+\]",
        r"\[Slide\s+\d+\]",
        r"chunk:\d+",
    ]

    anchors: list[str] = []

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            normalized = match.strip()
            if normalized not in anchors:
                anchors.append(normalized)

            if len(anchors) >= max_anchors:
                return anchors

    return anchors


def extractive_summary(
    text: str,
    sentence_count: int = DEFAULT_EXTRACTIVE_SENTENCE_COUNT,
    summarizer_name: SummarizerName = "lexrank",
    language: str = "english",
) -> ExtractiveSummaryResult:
    """
    Produce an extractive summary using a configurable Sumy summarizer.

    Returns:
        ExtractiveSummaryResult:
            - compressed_text
            - metadata:
                - summarizer_name
                - sentence_count
                - original_length
                - compressed_length
                - source_anchors
    """
    cleaned = _validate_text_for_summary(text)
    validated_sentence_count = _validate_sentence_count(sentence_count)

    context = _context(
        operation="extractive_summary",
        text=cleaned,
        sentence_count=validated_sentence_count,
        summarizer_name=summarizer_name,
        language=language,
    )

    logger.info(
        "Extractive summarization started",
        extra={"context": context},
    )

    try:
        parser = PlaintextParser.from_string(cleaned, Tokenizer(language))
        summarizer = _get_sumy_summarizer(summarizer_name)

        sentences = summarizer(parser.document, validated_sentence_count)
        compressed = " ".join(str(sentence) for sentence in sentences).strip()

    except ValueError:
        raise

    except Exception as exc:
        logger.exception(
            "Extractive summarization failed",
            extra={"context": context},
        )
        raise ValueError(
            f"Extractive summarization failed using {summarizer_name}."
        ) from exc

    if not compressed:
        logger.warning(
            "Extractive summarization produced empty output",
            extra={"context": context},
        )
        raise ValueError("Extractive summarization produced empty output.")

    metadata = {
        "summarizer_name": summarizer_name,
        "sentence_count": validated_sentence_count,
        "original_length": len(cleaned),
        "compressed_length": len(compressed),
        "source_anchors": _extract_source_anchors(cleaned),
    }

    logger.info(
        "Extractive summarization completed",
        extra={
            "context": {
                **context,
                "compressed_length": len(compressed),
                "source_anchor_count": len(metadata["source_anchors"]),
            }
        },
    )

    return ExtractiveSummaryResult(
        compressed_text=compressed,
        metadata=metadata,
    )


def build_summary_prompt(
    extractive: str,
    *,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Build a structured prompt for abstractive summarization.

    Sections:
    - Title
    - Requirements
    - Material
    - Citations / Source Anchors
    """
    if not isinstance(extractive, str) or not extractive.strip():
        raise ValueError("extractive text must be non-empty before building prompt.")

    metadata = metadata or {}
    title_text = title or metadata.get("title") or "Study Notes"

    source_anchors = metadata.get("source_anchors") or _extract_source_anchors(extractive)
    source_anchor_text = (
        "\n".join(f"- {anchor}" for anchor in source_anchors)
        if source_anchors
        else "- No explicit page, slide, or chunk anchors were detected."
    )

    contextual_metadata_lines: list[str] = []

    for key in (
        "kind",
        "original_path",
        "stored_path",
        "extension",
        "page_count",
        "slide_count",
        "duration",
        "sentence_count",
        "summarizer_name",
        "original_length",
        "compressed_length",
    ):
        if key in metadata and metadata[key] is not None:
            contextual_metadata_lines.append(f"- {key}: {metadata[key]}")

    contextual_metadata = (
        "\n".join(contextual_metadata_lines)
        if contextual_metadata_lines
        else "- No additional metadata provided."
    )

    return f"""
# Title

{title_text}

# Requirements

Create high-quality study notes from the material below.

You must:
- Use clear Markdown.
- Include key ideas, definitions, formulas if present, examples, and review questions.
- Preserve factual accuracy.
- Do not invent content.
- If the source is unclear, say so.
- Preserve visible page, slide, or chunk references when available.
- Add a final section titled "Citations / Source Anchors".
- Keep the notes concise but exam-ready.

# Context Metadata

{contextual_metadata}

# Material

{extractive.strip()}

# Citations / Source Anchors Available In Source

{source_anchor_text}
""".strip()


def summarize_document_text(
    text: str,
    *,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    llm: OllamaClient | None = None,
    model_name: str = OLLAMA_MODEL,
    summarizer_name: SummarizerName = "lexrank",
    sentence_count: int = DEFAULT_EXTRACTIVE_SENTENCE_COUNT,
    temperature: float = 0.15,
    max_tokens: int = 2500,
) -> SummaryResult:
    """
    Summarize document text using:
    1. Extractive compression via Sumy.
    2. Abstractive Markdown note generation via Ollama.

    Returns:
        SummaryResult:
            - markdown_notes
            - model_name
            - tokens_used
            - metadata
    """
    cleaned = _validate_text_for_summary(text)

    context = _context(
        operation="summarize_document_text",
        model_name=model_name,
        text=cleaned,
        sentence_count=sentence_count,
        summarizer_name=summarizer_name,
        tokens_requested=max_tokens,
        title=title,
    )

    logger.info(
        "Document summarization started",
        extra={"context": context},
    )

    client = llm or OllamaClient(model=model_name)

    try:
        if not client.healthcheck():
            raise ModelUnavailableError(
                "Ollama healthcheck failed",
                context={
                    **context,
                    "stage": "healthcheck",
                },
            )

        extractive_result = extractive_summary(
            cleaned,
            sentence_count=sentence_count,
            summarizer_name=summarizer_name,
        )

        prompt_metadata = {
            **(metadata or {}),
            **extractive_result.metadata,
            "title": title,
        }

        prompt = build_summary_prompt(
            extractive_result.compressed_text,
            title=title,
            metadata=prompt_metadata,
        )

        prompt_context = {
            **context,
            "prompt_length": len(prompt),
            "extractive_length": len(extractive_result.compressed_text),
            "compressed_length": extractive_result.metadata["compressed_length"],
        }

        logger.info(
            "LLM summarization request started",
            extra={"context": prompt_context},
        )

        generation = client.generate(
            prompt=prompt,
            system=DEFAULT_SUMMARY_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        result = SummaryResult(
            markdown_notes=generation.response_text,
            model_name=generation.model_name,
            tokens_used=generation.tokens_used,
            metadata={
                "extractive_length": len(extractive_result.compressed_text),
                "compressed_length": extractive_result.metadata["compressed_length"],
                "sentence_count": extractive_result.metadata["sentence_count"],
                "summarizer_name": extractive_result.metadata["summarizer_name"],
                "original_length": extractive_result.metadata["original_length"],
                "source_anchors": extractive_result.metadata.get("source_anchors", []),
                "temperature": temperature,
                "tokens_requested": max_tokens,
                "prompt_length": len(prompt),
                "llm_metadata": generation.metadata,
            },
        )

        logger.info(
            "Document summarization completed",
            extra={
                "context": {
                    **prompt_context,
                    "response_length": len(result.markdown_notes),
                    "tokens_used": result.tokens_used,
                }
            },
        )

        return result

    except ModelUnavailableError as exc:
        error_context = {
            **context,
            "stage": "llm_summarization",
            "error_context": getattr(exc, "context", {}),
        }

        logger.exception(
            "LLM summarization failed",
            extra={"context": error_context},
        )

        raise ModelUnavailableError(
            "Document summarization failed because the local model is unavailable.",
            context=error_context,
        ) from exc

    except ValueError:
        raise

    except Exception as exc:
        error_context = {
            **context,
            "stage": "summarize_document_text",
        }

        logger.exception(
            "Unexpected summarization failure",
            extra={"context": error_context},
        )

        raise ModelUnavailableError(
            "Document summarization failed.",
            context=error_context,
        ) from exc