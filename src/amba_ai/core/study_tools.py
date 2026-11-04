# src/amba_ai/core/study_tools.py
from __future__ import annotations

import json
import re
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Sequence, TypeVar

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.config import MAX_FLASHCARDS_PER_SESSION
from amba_ai.exceptions import IngestionError, ModelUnavailableError
from amba_ai.logger import logger
from amba_ai.models.schemas import Flashcard, MCQ


SOURCE_TEXT_LIMIT_CHARS = 12_000

MIN_FLASHCARDS = 10
MAX_FLASHCARDS = 20

MIN_MCQS = 5
MAX_MCQS = 20


T = TypeVar("T")


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------


def _context(
    *,
    operation: str,
    count: int | None = None,
    source_text: str | None = None,
    prompt: str | None = None,
    response_text: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "operation": operation,
    }

    if count is not None:
        context["count_requested"] = count

    if source_text is not None:
        context["source_text_length"] = len(source_text)

    if prompt is not None:
        context["prompt_length"] = len(prompt)

    if response_text is not None:
        context["response_length"] = len(response_text)

    context.update(extra)
    return context


def _validate_source_text(source_text: str) -> str:
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("source_text must be a non-empty string.")

    return source_text.strip()


def _validate_count(
    *,
    count: int,
    min_count: int,
    max_count: int,
    label: str,
) -> int:
    if not isinstance(count, int):
        raise ValueError(f"{label} count must be an integer.")

    if count < min_count or count > max_count:
        raise ValueError(
            f"{label} count must be between {min_count} and {max_count}."
        )

    return count


def _extract_source_anchors(source_text: str, max_anchors: int = 40) -> list[str]:
    """
    Extract contextual anchors from source text.

    Supports:
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
        for match in re.findall(pattern, source_text, flags=re.IGNORECASE):
            normalized = match.strip()

            if normalized not in anchors:
                anchors.append(normalized)

            if len(anchors) >= max_anchors:
                return anchors

    return anchors


def _strip_json_code_fence(text: str) -> str:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    return cleaned


def parse_json_array_strict(
    text: str,
    *,
    operation: str,
    context: dict[str, Any],
) -> list[Any]:
    """
    Parse an LLM response as a JSON array.

    Raises:
        IngestionError: if the response does not contain valid JSON array data.
    """
    cleaned = _strip_json_code_fence(text)

    try:
        parsed = json.loads(cleaned)

    except json.JSONDecodeError:
        # Fallback: try extracting the first JSON array.
        match = re.search(r"\[[\s\S]*\]", cleaned)

        if not match:
            logger.warning(
                "LLM response did not contain a JSON array",
                extra={"context": context},
            )
            raise IngestionError(
                "LLM response did not contain a valid JSON array.",
                context={
                    **context,
                    "stage": operation,
                    "error_type": "json_array_not_found",
                },
            )

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning(
                "Failed to parse JSON array from LLM response",
                extra={
                    "context": {
                        **context,
                        "error_type": "json_decode_error",
                    }
                },
            )
            raise IngestionError(
                "Failed to parse JSON array from LLM response.",
                context={
                    **context,
                    "stage": operation,
                    "error_type": "json_decode_error",
                },
            ) from exc

    if not isinstance(parsed, list):
        logger.warning(
            "LLM response JSON was not an array",
            extra={
                "context": {
                    **context,
                    "parsed_type": type(parsed).__name__,
                }
            },
        )
        raise IngestionError(
            "LLM response JSON must be an array.",
            context={
                **context,
                "stage": operation,
                "error_type": "json_not_array",
                "parsed_type": type(parsed).__name__,
            },
        )

    return parsed


def _build_dto(dto_cls: type[T], data: dict[str, Any]) -> T:
    """
    Construct dataclass DTOs while tolerating schemas that do not include
    optional DB-only fields.
    """
    if not is_dataclass(dto_cls):
        return dto_cls(**data)  # type: ignore[misc, call-arg]

    allowed = {field.name for field in fields(dto_cls)}
    filtered = {key: value for key, value in data.items() if key in allowed}
    return dto_cls(**filtered)  # type: ignore[call-arg]


def _normalize_source_ref(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


# ---------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------


def build_flashcards_prompt(
    *,
    source_text: str,
    count: int,
) -> str:
    anchors = _extract_source_anchors(source_text)
    anchors_text = (
        "\n".join(f"- {anchor}" for anchor in anchors)
        if anchors
        else "- No explicit page, slide, or chunk anchors detected."
    )

    prompt = f"""
Generate exactly {count} high-quality study flashcards from the source.

Return valid JSON only.
Do not include Markdown.
Do not include explanations outside JSON.
The top-level value must be a JSON array.

Schema:
[
  {{
    "question": "string",
    "answer": "string",
    "source_ref": "string or null"
  }}
]

Strict rules:
- Generate exactly {count} items.
- Every item must be an object.
- "question" must be a non-empty string.
- "answer" must be a non-empty string.
- "source_ref" must be a string copied from an available source anchor, or null.
- Use only the source content.
- Do not hallucinate.
- Prefer concepts, definitions, causes, effects, comparisons, formulas, and examples.
- Answers must be short but complete.
- If a relevant page, slide, or chunk marker appears near the evidence, use it as source_ref.

Available source anchors:
{anchors_text}

Source:
{source_text[:SOURCE_TEXT_LIMIT_CHARS]}
""".strip()

    logger.info(
        "Flashcards prompt created",
        extra={
            "context": _context(
                operation="build_flashcards_prompt",
                count=count,
                source_text=source_text,
                prompt=prompt,
                source_anchor_count=len(anchors),
            )
        },
    )

    return prompt


def build_mcqs_prompt(
    *,
    source_text: str,
    count: int,
) -> str:
    anchors = _extract_source_anchors(source_text)
    anchors_text = (
        "\n".join(f"- {anchor}" for anchor in anchors)
        if anchors
        else "- No explicit page, slide, or chunk anchors detected."
    )

    prompt = f"""
Generate exactly {count} multiple-choice questions from the source.

Return valid JSON only.
Do not include Markdown.
Do not include explanations outside JSON.
The top-level value must be a JSON array.

Schema:
[
  {{
    "question": "string",
    "choices": ["string", "string", "string", "string"],
    "correct_answer": "string",
    "explanation": "string",
    "source_ref": "string or null"
  }}
]

Strict rules:
- Generate exactly {count} items.
- Every item must be an object.
- "question" must be a non-empty string.
- "choices" must contain exactly 4 non-empty strings.
- "correct_answer" must exactly match one of the 4 choices.
- There must be exactly one correct answer.
- "explanation" must be a non-empty string.
- "source_ref" must be a string copied from an available source anchor, or null.
- Use only the source content.
- Do not hallucinate.
- Distractors must be plausible but clearly incorrect.
- If a relevant page, slide, or chunk marker appears near the evidence, use it as source_ref.

Available source anchors:
{anchors_text}

Source:
{source_text[:SOURCE_TEXT_LIMIT_CHARS]}
""".strip()

    logger.info(
        "MCQs prompt created",
        extra={
            "context": _context(
                operation="build_mcqs_prompt",
                count=count,
                source_text=source_text,
                prompt=prompt,
                source_anchor_count=len(anchors),
            )
        },
    )

    return prompt


# ---------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------


def _validate_flashcard_item(
    item: Any,
    *,
    index: int,
    context: dict[str, Any],
) -> Flashcard | None:
    if not isinstance(item, dict):
        logger.warning(
            "Flashcard validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "item_not_object",
                }
            },
        )
        return None

    question = item.get("question")
    answer = item.get("answer")

    if not isinstance(question, str) or not question.strip():
        logger.warning(
            "Flashcard validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "empty_question",
                }
            },
        )
        return None

    if not isinstance(answer, str) or not answer.strip():
        logger.warning(
            "Flashcard validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "empty_answer",
                }
            },
        )
        return None

    data = {
        "question": question.strip(),
        "answer": answer.strip(),
        "source_ref": _normalize_source_ref(item.get("source_ref")),
    }

    return _build_dto(Flashcard, data)


def generate_flashcards(
    source_text: str,
    count: int = MAX_FLASHCARDS_PER_SESSION,
    llm: OllamaClient | None = None,
) -> list[Flashcard]:
    cleaned_source = _validate_source_text(source_text)
    validated_count = _validate_count(
        count=count,
        min_count=MIN_FLASHCARDS,
        max_count=MAX_FLASHCARDS,
        label="flashcards",
    )

    context = _context(
        operation="generate_flashcards",
        count=validated_count,
        source_text=cleaned_source,
    )

    client = llm or OllamaClient()
    prompt = build_flashcards_prompt(
        source_text=cleaned_source,
        count=validated_count,
    )

    try:
        generation = client.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=2500,
        )
        response_text = generation.response_text

    except ModelUnavailableError:
        raise

    except Exception as exc:
        logger.exception(
            "Flashcard generation failed",
            extra={"context": context},
        )
        raise ModelUnavailableError(
            "Flashcard generation failed.",
            context={
                **context,
                "stage": "llm_generate",
            },
        ) from exc

    parse_context = {
        **context,
        "response_length": len(response_text),
    }

    items = parse_json_array_strict(
        response_text,
        operation="generate_flashcards",
        context=parse_context,
    )

    valid: list[Flashcard] = []

    for index, item in enumerate(items):
        card = _validate_flashcard_item(
            item,
            index=index,
            context=parse_context,
        )
        if card is not None:
            valid.append(card)

    if len(valid) < validated_count:
        logger.warning(
            "Flashcard generation returned fewer valid items than requested",
            extra={
                "context": {
                    **parse_context,
                    "valid_count": len(valid),
                    "expected_count": validated_count,
                }
            },
        )

    if not valid:
        raise IngestionError(
            "LLM returned no valid flashcards.",
            context={
                **parse_context,
                "stage": "validate_flashcards",
                "valid_count": 0,
            },
        )

    result = valid[:validated_count]

    logger.info(
        "Flashcard generation succeeded",
        extra={
            "context": {
                **parse_context,
                "valid_count": len(result),
                "model_name": generation.model_name,
                "tokens_used": generation.tokens_used,
            }
        },
    )

    return result


# ---------------------------------------------------------------------
# MCQs
# ---------------------------------------------------------------------


def _validate_mcq_item(
    item: Any,
    *,
    index: int,
    context: dict[str, Any],
) -> MCQ | None:
    if not isinstance(item, dict):
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "item_not_object",
                }
            },
        )
        return None

    question = item.get("question")
    choices = item.get("choices")
    correct_answer = item.get("correct_answer")
    explanation = item.get("explanation")

    if not isinstance(question, str) or not question.strip():
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "empty_question",
                }
            },
        )
        return None

    if not isinstance(choices, list) or len(choices) != 4:
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "choices_not_exactly_four",
                }
            },
        )
        return None

    normalized_choices = []

    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            logger.warning(
                "MCQ validation failed",
                extra={
                    "context": {
                        **context,
                        "index": index,
                        "reason": "empty_choice",
                    }
                },
            )
            return None

        normalized_choices.append(choice.strip())

    if len(set(normalized_choices)) != 4:
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "duplicate_choices",
                }
            },
        )
        return None

    if not isinstance(correct_answer, str) or not correct_answer.strip():
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "empty_correct_answer",
                }
            },
        )
        return None

    normalized_correct = correct_answer.strip()

    if normalized_correct not in normalized_choices:
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "correct_answer_not_in_choices",
                }
            },
        )
        return None

    if not isinstance(explanation, str) or not explanation.strip():
        logger.warning(
            "MCQ validation failed",
            extra={
                "context": {
                    **context,
                    "index": index,
                    "reason": "empty_explanation",
                }
            },
        )
        return None

    data = {
        "question": question.strip(),
        "choices": normalized_choices,
        "correct_answer": normalized_correct,
        "explanation": explanation.strip(),
        "source_ref": _normalize_source_ref(item.get("source_ref")),
    }

    return _build_dto(MCQ, data)


def generate_mcqs(
    source_text: str,
    count: int = 10,
    llm: OllamaClient | None = None,
) -> list[MCQ]:
    cleaned_source = _validate_source_text(source_text)
    validated_count = _validate_count(
        count=count,
        min_count=MIN_MCQS,
        max_count=MAX_MCQS,
        label="MCQs",
    )

    context = _context(
        operation="generate_mcqs",
        count=validated_count,
        source_text=cleaned_source,
    )

    client = llm or OllamaClient()
    prompt = build_mcqs_prompt(
        source_text=cleaned_source,
        count=validated_count,
    )

    try:
        generation = client.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=3000,
        )
        response_text = generation.response_text

    except ModelUnavailableError:
        raise

    except Exception as exc:
        logger.exception(
            "MCQ generation failed",
            extra={"context": context},
        )
        raise ModelUnavailableError(
            "MCQ generation failed.",
            context={
                **context,
                "stage": "llm_generate",
            },
        ) from exc

    parse_context = {
        **context,
        "response_length": len(response_text),
    }

    items = parse_json_array_strict(
        response_text,
        operation="generate_mcqs",
        context=parse_context,
    )

    valid: list[MCQ] = []

    for index, item in enumerate(items):
        mcq = _validate_mcq_item(
            item,
            index=index,
            context=parse_context,
        )
        if mcq is not None:
            valid.append(mcq)

    if len(valid) < validated_count:
        logger.warning(
            "MCQ generation returned fewer valid items than requested",
            extra={
                "context": {
                    **parse_context,
                    "valid_count": len(valid),
                    "expected_count": validated_count,
                }
            },
        )

    if not valid:
        raise IngestionError(
            "LLM returned no valid MCQs.",
            context={
                **parse_context,
                "stage": "validate_mcqs",
                "valid_count": 0,
            },
        )

    result = valid[:validated_count]

    logger.info(
        "MCQ generation succeeded",
        extra={
            "context": {
                **parse_context,
                "valid_count": len(result),
                "model_name": generation.model_name,
                "tokens_used": generation.tokens_used,
            }
        },
    )

    return result


# ---------------------------------------------------------------------
# Dict conversion helpers for legacy callers / database insertion
# ---------------------------------------------------------------------


def flashcards_to_dicts(cards: Sequence[Flashcard]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for card in cards:
        item = asdict(card) if is_dataclass(card) else dict(card)  # type: ignore[arg-type]

        output.append(
            {
                "question": str(item["question"]).strip(),
                "answer": str(item["answer"]).strip(),
                "source_ref": item.get("source_ref"),
            }
        )

    return output


def mcqs_to_dicts(mcqs: Sequence[MCQ]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for mcq in mcqs:
        item = asdict(mcq) if is_dataclass(mcq) else dict(mcq)  # type: ignore[arg-type]

        output.append(
            {
                "question": str(item["question"]).strip(),
                "choices": [str(choice).strip() for choice in item["choices"]],
                "correct_answer": str(item["correct_answer"]).strip(),
                "explanation": str(item["explanation"]).strip(),
                "source_ref": item.get("source_ref"),
            }
        )

    return output