from __future__ import annotations

import random
import re
import threading
import time
from typing import Any, Callable, Protocol, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.config import OLLAMA_STRUCTURED_MODEL, OLLAMA_SUMMARY_MODEL
from amba_ai.core.content_delivery import (
    SCHEMA_VERSION,
    build_fast_summary,
    fill_missing_flashcards,
    normalize_card,
    normalize_mcq,
)
from amba_ai.learning.domain_plugin import DomainPlugin
from amba_ai.learning.domain_registry import DomainRegistry, domain_registry
from amba_ai.logger import logger
from amba_ai.models.schemas import Flashcard, MCQ, StudyAssetsResult, SummaryResult
from amba_ai.services.semantic_validators import (
    FlashcardSemanticValidator,
    MCQSemanticValidator,
    SemanticQualityGateError,
    StudyAssetQualityAssessor,
    SummarySemanticValidator,
    normalize_summary_structure,
)

MAX_FLASHCARDS = 50
MAX_MCQS = 50
MAX_INPUT_CHARS = 100_000
MAX_TITLE_CHARS = 300

T = TypeVar("T")


class LLMResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    response_text: str
    model_name: str = "llm"
    tokens_used: int = 0


class LLMProvider(Protocol):
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, client: OllamaClient | None = None) -> None:
        self.model = model
        self.client = client or OllamaClient(model=model)

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        gen = self.client.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return LLMResponse(
            response_text=str(getattr(gen, "response_text", "") or ""),
            model_name=str(getattr(gen, "model_name", self.model)),
            tokens_used=int(getattr(gen, "tokens_used", 0) or 0),
        )


class MetricsProvider(Protocol):
    def record_summary(self, success: bool, duration: float, tokens: int = 0) -> None: ...
    def record_assets(self, success: bool, duration: float, tokens: int = 0) -> None: ...
    def record_fallback(self) -> None: ...
    def record_circuit_trip(self) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...


class FallbackGenerator(Protocol):
    def extractive_notes(
        self,
        text: str,
        title: str,
        *,
        document_id: int | None = None,
        source_name: str | None = None,
        reason: str | None = None,
    ) -> SummaryResult: ...
    def synthesize_flashcards(self, text: str, title: str, needed: int) -> list[Flashcard]: ...
    def synthesize_mcqs(self, text: str, title: str, needed: int) -> list[MCQ]: ...


class DefaultFallbackGenerator(FallbackGenerator):
    def extractive_notes(
        self,
        text: str,
        title: str,
        *,
        document_id: int | None = None,
        source_name: str | None = None,
        reason: str | None = None,
    ) -> SummaryResult:
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
        summary_body = (
            paragraphs[0]
            if paragraphs
            else "Source text successfully ingested and indexed for curriculum review."
        )
        body_notes = "\n\n".join(paragraphs[1:6]) if len(paragraphs) > 1 else summary_body

        effective_title = source_name or title
        source_line = (
            f"- {effective_title}, local document ID {document_id}"
            if document_id is not None
            else f"- {effective_title}"
        )

        markdown = (
            f"# {title}\n\n"
            f"## Executive Summary\n{summary_body}\n\n"
            f"## Core Concepts\nKey conceptual and structural principles established in the primary curriculum source.\n\n"
            f"## Structured Study Notes\n{body_notes}\n\n"
            f"## Sources\n{source_line}"
        )

        doc_ids = [document_id] if document_id is not None else []
        citations = [
            {
                "document_id": document_id,
                "source_name": effective_title,
                "source_type": "local_document",
            }
        ] if document_id is not None else []

        metadata: dict[str, Any] = {
            "fallback": True,
            "fallback_reason": str(reason or "deterministic_extractive_fallback"),
            "schema_version": SCHEMA_VERSION,
            "document_id": document_id,
            "source_document_ids": doc_ids,
            "citations": citations,
        }

        return SummaryResult(
            markdown_notes=markdown,
            model_name="fallback-extractive",
            tokens_used=0,
            metadata=metadata,
        )

    def synthesize_flashcards(self, text: str, title: str, needed: int) -> list[Flashcard]:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if 30 <= len(s.strip()) <= 200
        ]
        cards: list[Flashcard] = []

        for idx, sentence in enumerate(sentences[:needed], 1):
            cards.append(
                Flashcard(
                    question=f"What key fact is established regarding section {idx} of {title}?",
                    answer=sentence,
                    source_ref=title,
                )
            )

        while len(cards) < needed:
            idx = len(cards) + 1
            cards.append(
                Flashcard(
                    question=f"What is the designated core objective for learning phase {idx}?",
                    answer=f"Verified study material establishes key mechanisms documented under {title}.",
                    source_ref=title,
                )
            )

        return cards

    def synthesize_mcqs(self, text: str, title: str, needed: int) -> list[MCQ]:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if 35 <= len(s.strip()) <= 180
        ]
        mcqs: list[MCQ] = []

        if len(sentences) < 4:
            sentences.extend(
                [
                    f"The foundational concept is established in the primary documentation of {title}.",
                    f"Core analytical principles require systematic application of {title}.",
                    "Systematic verification relies on primary evidence established in the text.",
                    "The designated framework establishes validated conceptual boundaries.",
                ]
            )

        for idx in range(needed):
            anchor_idx = idx % len(sentences)
            correct_choice = sentences[anchor_idx]

            pool = [s for j, s in enumerate(sentences) if j != anchor_idx]
            distractors = pool[:3]
            while len(distractors) < 3:
                distractors.append(
                    f"This proposition contradicts the findings documented in {title}."
                )

            choices = [correct_choice, distractors[0], distractors[1], distractors[2]]

            mcqs.append(
                MCQ(
                    question=f"Which proposition represents the verified finding for section {idx + 1}?",
                    choices=[choices[0], choices[1], choices[2], choices[3]],
                    correct_answer=correct_choice,
                    explanation=f"The primary source text directly validates: {correct_choice}",
                    source_ref=title,
                )
            )

        return mcqs


class FlashcardSchema(BaseModel):
    question: str
    answer: str
    source_ref: str | None = None


class MCQSchema(BaseModel):
    question: str
    choices: list[str] = Field(min_length=4, max_length=4)
    correct_answer: str
    explanation: str
    source_ref: str | None = None


class StudyAssetsSchema(BaseModel):
    flashcards: list[FlashcardSchema] = Field(default_factory=list)
    mcqs: list[MCQSchema] = Field(default_factory=list)


class ContentDeliveryMetrics(MetricsProvider):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.summary_success_count: int = 0
        self.summary_failure_count: int = 0
        self.asset_success_count: int = 0
        self.asset_failure_count: int = 0
        self.fallback_invocations: int = 0
        self.circuit_breaker_trips: int = 0
        self.total_tokens_consumed: int = 0
        self.total_latency_seconds: float = 0.0

    def record_summary(self, success: bool, duration: float, tokens: int = 0) -> None:
        with self._lock:
            if success:
                self.summary_success_count += 1
            else:
                self.summary_failure_count += 1
            self.total_latency_seconds += duration
            self.total_tokens_consumed += tokens

    def record_assets(self, success: bool, duration: float, tokens: int = 0) -> None:
        with self._lock:
            if success:
                self.asset_success_count += 1
            else:
                self.asset_failure_count += 1
            self.total_latency_seconds += duration
            self.total_tokens_consumed += tokens

    def record_fallback(self) -> None:
        with self._lock:
            self.fallback_invocations += 1

    def record_circuit_trip(self) -> None:
        with self._lock:
            self.circuit_breaker_trips += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_requests = (
                self.summary_success_count
                + self.summary_failure_count
                + self.asset_success_count
                + self.asset_failure_count
            )
            return {
                "summary_success": self.summary_success_count,
                "summary_failure": self.summary_failure_count,
                "asset_success": self.asset_success_count,
                "asset_failure": self.asset_failure_count,
                "fallback_count": self.fallback_invocations,
                "circuit_trips": self.circuit_breaker_trips,
                "total_tokens": self.total_tokens_consumed,
                "total_requests": total_requests,
                "avg_latency": round(
                    self.total_latency_seconds / max(1, total_requests),
                    3,
                ),
            }


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 60.0,
        on_trip: Callable[[], None] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.on_trip = on_trip
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state: str = "CLOSED"
        self._lock = threading.Lock()

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"

    def record_failure(self) -> None:
        tripped = False
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold and self.state != "OPEN":
                self.state = "OPEN"
                tripped = True

        if tripped and self.on_trip:
            self.on_trip()

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.reset_timeout:
                    self.state = "HALF-OPEN"
                    return True
                return False
            return True


class RetryPolicy:
    def __init__(
        self,
        max_attempts: int = 2,
        initial_backoff: float = 0.5,
        backoff_multiplier: float = 2.0,
        jitter_max: float = 0.2,
        sleeper: Callable[[float], None] = time.sleep,
        rng: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.backoff_multiplier = backoff_multiplier
        self.jitter_max = jitter_max
        self.sleeper = sleeper
        self.rng = rng

    def execute(self, action: Callable[[], T]) -> T:
        delay = self.initial_backoff
        last_exception: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return action()
            except Exception as exc:
                last_exception = exc
                if attempt == self.max_attempts:
                    break
                jitter = self.rng(0.0, self.jitter_max) if self.jitter_max > 0.0 else 0.0
                self.sleeper(delay + jitter)
                delay *= self.backoff_multiplier

        raise last_exception or RuntimeError("Retry sequence terminated without exception state")


class ContentDeliveryService:
    def __init__(
        self,
        structured_llm: LLMProvider | None = None,
        summary_llm: LLMProvider | None = None,
        registry: DomainRegistry | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retry_policy: RetryPolicy | None = None,
        metrics: MetricsProvider | None = None,
        fallback_generator: FallbackGenerator | None = None,
    ) -> None:
        self.structured_llm = structured_llm or OllamaProvider(model=OLLAMA_STRUCTURED_MODEL)
        self.summary_llm = summary_llm or OllamaProvider(model=OLLAMA_SUMMARY_MODEL)
        self.registry = registry or domain_registry
        self.metrics = metrics or ContentDeliveryMetrics()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            on_trip=self.metrics.record_circuit_trip
        )
        self.transport_retry_policy = retry_policy or RetryPolicy(max_attempts=2, initial_backoff=0.5)
        self.retry_policy = self.transport_retry_policy
        self.fallback_generator = fallback_generator or DefaultFallbackGenerator()

    def _resolve_domain_plugin(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> DomainPlugin | None:
        if hasattr(self.registry, "resolve_plugin"):
            return self.registry.resolve_plugin(text, metadata)
        adapter = self.registry.resolve(text, metadata)
        if adapter and hasattr(self.registry, "get_plugin"):
            return self.registry.get_plugin(adapter.name)
        if isinstance(adapter, DomainPlugin):
            return adapter
        return None

    def _repair_summary_format(
        self,
        candidate_notes: str,
        title: str,
        validation_error: SemanticQualityGateError,
        document_id: int | None = None,
    ) -> SummaryResult:
        source_ref = f"- {title}, local document ID {document_id}" if document_id is not None else f"- {title}"
        repair_prompt = (
            f"Reformat the following draft study notes into strict Markdown hierarchy without adding new facts.\n"
            f"Required headings:\n"
            f"# {title}\n"
            f"## Executive Summary\n"
            f"## Core Concepts\n"
            f"## Structured Study Notes\n"
            f"## Sources\n\n"
            f"Under '## Sources', include:\n{source_ref}\n\n"
            f"CONTENT TO REFORMAT:\n{candidate_notes[:8000]}"
        )
        gen = self.summary_llm.generate(prompt=repair_prompt, temperature=0.0, max_tokens=1500)
        repaired_md = gen.response_text.strip()
        doc_ids = [document_id] if document_id is not None else []
        citations = [
            {
                "document_id": document_id,
                "source_name": title,
                "source_type": "local_document",
            }
        ] if document_id is not None else []
        result = SummaryResult(
            markdown_notes=repaired_md,
            model_name=gen.model_name,
            tokens_used=gen.tokens_used,
            metadata={
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "source_document_ids": doc_ids,
                "citations": citations,
                "format_repaired": True,
            },
        )
        return SummarySemanticValidator.validate(result)

    def _validated_extractive_fallback(self, text: str, title: str, *, document_id: int | None, source_name: str, reason: str) -> SummaryResult:
        fallback = self.fallback_generator.extractive_notes(text, title, document_id=document_id, source_name=source_name, reason=reason)
        return SummarySemanticValidator.validate(normalize_summary_structure(fallback))

    def generate_study_notes(
        self,
        raw_text: str,
        title: str,
        *,
        document_id: int | None = None,
        source_name: str | None = None,
    ) -> SummaryResult:
        start_time = time.perf_counter()
        bounded_text = str(raw_text or "").strip()[:MAX_INPUT_CHARS]
        bounded_title = str(title or "Study Notes").strip()[:MAX_TITLE_CHARS]
        effective_source = source_name or bounded_title

        doc_ids = [document_id] if document_id is not None else []
        base_citations = [
            {
                "document_id": document_id,
                "source_name": effective_source,
                "source_type": "local_document",
            }
        ] if document_id is not None else []

        if not self.circuit_breaker.allow_request():
            self.metrics.record_fallback()
            logger.warning("Circuit breaker OPEN; utilizing safe extractive synthesis")
            return self._validated_extractive_fallback(
                bounded_text, bounded_title, document_id=document_id,
                source_name=effective_source, reason="circuit_breaker_open",
            )

        source_annotation = (
            f"- {effective_source}, local document ID {document_id}"
            if document_id is not None
            else f"- {effective_source}"
        )

        prompt = (
            f"Generate rigorous academic study notes using this exact Markdown hierarchy:\n"
            f"# {bounded_title}\n## Executive Summary\n## Core Concepts\n"
            f"## Structured Study Notes\n## Sources\n\n"
            f"Under '## Sources', cite: {source_annotation}\n\n"
            f"SOURCE:\n{bounded_text[:16000]}"
        )

        def _perform_transport_generation() -> LLMResponse:
            return self.summary_llm.generate(prompt=prompt, temperature=0.12, max_tokens=1800)

        try:
            gen = self.transport_retry_policy.execute(_perform_transport_generation)
            self.circuit_breaker.record_success()
        except Exception as exc:
            self.circuit_breaker.record_failure()
            elapsed = time.perf_counter() - start_time
            self.metrics.record_summary(False, elapsed)
            self.metrics.record_fallback()
            logger.warning(
                "Primary summary LLM transport failed; fallback invoked",
                extra={"context": {"error": str(exc)}},
            )
            return self._validated_extractive_fallback(
                bounded_text, bounded_title, document_id=document_id,
                source_name=effective_source, reason=f"transport_failure: {exc}",
            )

        raw_result = SummaryResult(
            markdown_notes=gen.response_text.strip(),
            model_name=gen.model_name,
            tokens_used=gen.tokens_used,
            metadata={
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "source_document_ids": doc_ids,
                "citations": base_citations,
            },
        )

        normalized = normalize_summary_structure(raw_result)

        try:
            validated = SummarySemanticValidator.validate(normalized)
            elapsed = time.perf_counter() - start_time
            self.metrics.record_summary(True, elapsed, validated.tokens_used or 0)
            return validated
        except SemanticQualityGateError as val_err:
            logger.info("Semantic validation detected structural defect; attempting single format repair")
            try:
                repaired = self._repair_summary_format(
                    str(normalized.markdown_notes or ""),
                    bounded_title,
                    val_err,
                    document_id=document_id,
                )
                elapsed = time.perf_counter() - start_time
                self.metrics.record_summary(True, elapsed, (gen.tokens_used or 0) + (repaired.tokens_used or 0))
                return repaired
            except Exception as repair_err:
                self.metrics.record_fallback()
                logger.warning(
                    "Format repair failed; invoking deterministic extractive fallback",
                    extra={"context": {"validation_error": str(val_err), "repair_error": str(repair_err)}},
                )
                return self._validated_extractive_fallback(
                bounded_text, bounded_title, document_id=document_id,
                source_name=effective_source, reason=f"validation_failure: {val_err}",
            )

    def summarize_document(
        self,
        raw_text: str,
        title: str,
        *,
        document_id: int | None = None,
        source_name: str | None = None,
        notes_markdown: str | None = None,
    ) -> SummaryResult:
        doc_ids = [document_id] if document_id is not None else []
        citations = [
            {
                "document_id": document_id,
                "source_name": source_name or title,
                "source_type": "local_document",
            }
        ] if document_id is not None else []

        if notes_markdown:
            summary = build_fast_summary(notes_markdown, title, title)
            return SummaryResult(
                markdown_notes=summary,
                model_name="fast-path",
                tokens_used=0,
                metadata={
                    "fast_path": True,
                    "schema_version": SCHEMA_VERSION,
                    "document_id": document_id,
                    "source_document_ids": doc_ids,
                    "citations": citations,
                },
            )
        notes = self.generate_study_notes(
            raw_text,
            title,
            document_id=document_id,
            source_name=source_name,
        )
        summary = build_fast_summary(notes.markdown_notes, title, title)
        merged_metadata = dict(notes.metadata or {})
        merged_metadata.update({
            "fast_path": True,
            "schema_version": SCHEMA_VERSION,
            "document_id": document_id,
            "source_document_ids": doc_ids,
            "citations": citations,
        })
        return SummaryResult(
            markdown_notes=summary,
            model_name=notes.model_name,
            tokens_used=notes.tokens_used,
            metadata=merged_metadata,
        )

    def generate_study_assets(
        self,
        raw_text: str,
        title: str,
        flashcard_count: int = 10,
        mcq_count: int = 10,
    ) -> StudyAssetsResult:
        start_time = time.perf_counter()
        bounded_text = str(raw_text or "").strip()[:MAX_INPUT_CHARS]
        bounded_title = str(title or "Study Assets").strip()[:MAX_TITLE_CHARS]
        target_cards = max(1, min(flashcard_count, MAX_FLASHCARDS))
        target_mcqs = max(1, min(mcq_count, MAX_MCQS))

        prompt = (
            f"Return valid JSON matching this schema:\n"
            f"{{\"flashcards\": [{{'question': '', 'answer': '', 'source_ref': ''}}],\n"
            f"\"mcqs\": [{{'question': '', 'choices': ['', '', '', ''], 'correct_answer': '', 'explanation': '', 'source_ref': ''}}]}}\n\n"
            f"Generate exactly {target_cards} flashcards and {target_mcqs} MCQs.\n"
            f"Title: {bounded_title}\nSOURCE:\n{bounded_text[:14000]}"
        )

        raw_cards: list[Flashcard] = []
        raw_mcqs: list[MCQ] = []
        tokens_consumed = 0

        if self.circuit_breaker.allow_request():
            def _perform_asset_generation() -> StudyAssetsSchema:
                gen = self.structured_llm.generate(prompt=prompt, temperature=0.1, max_tokens=2500)
                clean_json = re.sub(
                    r"^```(?:json)?|```$",
                    "",
                    str(gen.response_text or "").strip(),
                    flags=re.MULTILINE,
                ).strip()
                nonlocal tokens_consumed
                tokens_consumed = gen.tokens_used
                return StudyAssetsSchema.model_validate_json(clean_json)

            try:
                parsed = self.transport_retry_policy.execute(_perform_asset_generation)
                self.circuit_breaker.record_success()

                for fc in parsed.flashcards:
                    card = normalize_card(fc.model_dump(), {"title": bounded_title})
                    if card:
                        raw_cards.append(card)

                for m in parsed.mcqs:
                    mcq = normalize_mcq(m.model_dump(), {"title": bounded_title})
                    if mcq:
                        raw_mcqs.append(mcq)
            except Exception as exc:
                self.circuit_breaker.record_failure()
                logger.warning(
                    "Structured asset extraction failed",
                    extra={"context": {"error": str(exc)}},
                )

        plugin = self._resolve_domain_plugin(bounded_text)
        if plugin:
            raw_cards = plugin.refine_flashcards(raw_cards, bounded_text)
            raw_mcqs = plugin.refine_mcqs(raw_mcqs, bounded_text)

        valid_cards = FlashcardSemanticValidator.filter_valid(raw_cards)
        valid_mcqs = MCQSemanticValidator.filter_valid(raw_mcqs)

        ranked_cards = StudyAssetQualityAssessor.filter_and_rank_flashcards(valid_cards)
        ranked_mcqs = StudyAssetQualityAssessor.filter_and_rank_mcqs(valid_mcqs)

        ranked_cards = fill_missing_flashcards(ranked_cards, target_cards, {"raw_text": bounded_text, "title": bounded_title})

        used_fallback = False
        if len(ranked_cards) < target_cards:
            used_fallback = True
            synthetic_cards = self.fallback_generator.synthesize_flashcards(
                bounded_text, bounded_title, target_cards - len(ranked_cards)
            )
            ranked_cards.extend(synthetic_cards)

        if len(ranked_mcqs) < target_mcqs:
            used_fallback = True
            synthetic_mcqs = self.fallback_generator.synthesize_mcqs(
                bounded_text, bounded_title, target_mcqs - len(ranked_mcqs)
            )
            ranked_mcqs.extend(synthetic_mcqs)

        if used_fallback:
            self.metrics.record_fallback()

        elapsed = time.perf_counter() - start_time
        self.metrics.record_assets(not used_fallback, elapsed, tokens_consumed)

        return StudyAssetsResult(
            flashcards=ranked_cards[:target_cards],
            mcqs=ranked_mcqs[:target_mcqs],
            metadata={
                "schema_version": SCHEMA_VERSION,
                "domain": plugin.domain_name if plugin else "general",
                "validated_cards": len(ranked_cards),
                "validated_mcqs": len(ranked_mcqs),
                "fallback_applied": used_fallback,
            },
        )