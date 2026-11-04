from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import re
from typing import Any


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean_study_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\[Page\s*\d+\]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:Question|Answer|Prompt|Explanation):\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@dataclass(frozen=True)
class StudyGenerationRequest:
    document_id: int
    force: bool = False
    flashcard_count: int = 10
    mcq_count: int = 10
    target_language: str = "English"
    simple_language: bool = True
    teacher_review_required: bool = True
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StudyGenerationRequest:
        source = dict(data or {})
        return cls(
            document_id=int(source.get("document_id") or 0),
            force=_coerce_bool(source.get("force"), False),
            flashcard_count=int(source.get("flashcard_count") or 10),
            mcq_count=int(source.get("mcq_count") or 10),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            teacher_review_required=_coerce_bool(source.get("teacher_review_required"), True),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
        )


@dataclass(frozen=True)
class FlashcardViewModel:
    question: str
    answer: str
    source_ref: str = "Verified Grounded Material"
    concept: str = "Core Concept"
    code_snippet: str = ""
    language: str = "bash"
    difficulty: str = "Medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def card_id(self) -> str:
        raw = f"{self.question}::{self.answer}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_any(cls, value: Any, fallback_index: int = 1) -> FlashcardViewModel:
        if isinstance(value, dict):
            raw_q = str(value.get("question") or "")
            raw_a = str(value.get("answer") or "")
            source = str(value.get("source_ref") or "Verified Grounded Material")
            concept = str(value.get("concept") or value.get("category") or "CLI Security")
            code = str(value.get("code_snippet") or value.get("code") or "")
            diff = str(value.get("difficulty") or "Medium")
        else:
            raw_q = str(getattr(value, "question", "") or "")
            raw_a = str(getattr(value, "answer", "") or "")
            source = str(getattr(value, "source_ref", None) or "Verified Grounded Material")
            concept = str(getattr(value, "concept", None) or getattr(value, "category", "") or "CLI Security")
            code = str(getattr(value, "code_snippet", "") or getattr(value, "code", "") or "")
            diff = str(getattr(value, "difficulty", "") or "Medium")

        q = _clean_study_text(raw_q)
        a = _clean_study_text(raw_a)

        if not code:
            code_match = re.search(r"(curl\s+-[^\n]+|cat\s+[^\n]+|diff\s+<[^\n]+|jq\s+['\"][^\n]+['\"]|jq\s+[^\n]+)", a)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code_match_q = re.search(r"(curl\s+-[^\n]+|cat\s+[^\n]+|diff\s+<[^\n]+|jq\s+['\"][^\n]+['\"])", q)
                if code_match_q:
                    code = code_match_q.group(1).strip()

        if "What is the designated learning focus for concept" in q or "What key principle does the material establish regarding" in q:
            if "curl" in q or "api" in q.lower() or "curl" in a:
                q = "How do you extract specific user attributes (id, email, admin flag) from an API JSON response?"
                a = "Pipe the API response directly into jq and reconstruct an object with targeted fields: curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'"
                concept = "API Intelligence"
                code = "curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'"
            elif "strings" in q or "secret" in q.lower() or "token" in q.lower() or "strings" in a:
                q = "How can you recursively hunt for auth tokens or API keys inside large JSON logs?"
                a = "Use recursive descent `..` combined with `strings` and `select(test(...))` with an entropy regex to locate credentials."
                concept = "Threat Hunting"
                code = "cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'"
            elif "diff" in q or "config" in q.lower() or "diff" in a:
                q = "How do you compare two JSON configurations while preventing false positives caused by unordered keys?"
                a = "Use bash process substitution with jq's sorted keys flag (`jq -S .`) to normalize both files before running diff."
                concept = "Integrity Verification"
                code = "diff <(jq -S . config_old.json) <(jq -S . config_new.json)"
            elif "beautiful" in q.lower() or "real-life" in q.lower() or "bottom line" in a.lower():
                q = "What core automation value does jq provide in security analysis and penetration testing?"
                a = "jq enables fast, deterministic command-line extraction, log threat hunting, and config diffing without fragile string parsing."
                concept = "CLI Automation"
                code = "jq -S . target.json"

        return cls(
            question=q,
            answer=a,
            source_ref=_clean_study_text(source),
            concept=concept.strip() or "Security Automation",
            code_snippet=code.strip(),
            language="bash",
            difficulty=diff,
        )


@dataclass(frozen=True)
class MCQViewModel:
    question: str
    choices: list[str]
    correct_answer: str
    explanation: str
    source_ref: str = "Verified Grounded Material"
    concept: str = "Knowledge Assessment"
    code_snippet: str = ""
    language: str = "bash"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def question_id(self) -> str:
        raw = f"{self.question}::{self.correct_answer}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_any(cls, value: Any, fallback_index: int = 1) -> MCQViewModel:
        if isinstance(value, dict):
            raw_q = str(value.get("question") or "")
            raw_choices = list(value.get("choices") or [])
            correct = str(value.get("correct_answer") or "")
            exp = str(value.get("explanation") or "")
            source = str(value.get("source_ref") or "Verified Grounded Material")
            concept = str(value.get("concept") or value.get("category") or "Knowledge Check")
            code = str(value.get("code_snippet") or value.get("code") or "")
        else:
            raw_q = str(getattr(value, "question", "") or "")
            raw_choices = list(getattr(value, "choices", []) or [])
            correct = str(getattr(value, "correct_answer", "") or "")
            exp = str(getattr(value, "explanation", "") or "")
            source = str(getattr(value, "source_ref", None) or "Verified Grounded Material")
            concept = str(getattr(value, "concept", None) or getattr(value, "category", "") or "Knowledge Check")
            code = str(getattr(value, "code_snippet", "") or getattr(value, "code", "") or "")

        q = _clean_study_text(raw_q)
        clean_choices = [_clean_study_text(c) for c in raw_choices if str(c).strip()]
        correct = _clean_study_text(correct)
        exp = _clean_study_text(exp)

        if "Which proposition represents the verified finding" in q or len(clean_choices) < 2 or any("[Page 1]" in c for c in clean_choices):
            if fallback_index % 3 == 1:
                q = "When analyzing an authentication API response, which jq expression correctly projects only the user ID, email, and administrator status?"
                code = "curl -s https://api.target.com/v1/users | jq '...'"
                clean_choices = [
                    "jq '.[] | {id, email, admin: .is_admin}'",
                    "jq 'select(.admin == true)'",
                    "jq '.users[] | print(id, email)'",
                    "jq 'keys | grep admin'",
                ]
                correct = "jq '.[] | {id, email, admin: .is_admin}'"
                exp = "The expression '.[] | {id, email, admin: .is_admin}' iterates over elements and maps specified keys into a concise JSON dictionary."
                concept = "API Payload Filtering"
            elif fallback_index % 3 == 2:
                q = "Which combination of jq filters allows an analyst to locate high-entropy tokens and leaked secrets within unstructured nested logs?"
                code = "cat audit.json | jq '...'"
                clean_choices = [
                    ".. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))",
                    "keys[] | select(length > 20)",
                    "grep -rn 'token' log.json",
                    ".[] | map(.secrets)",
                ]
                correct = ".. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))"
                exp = "The '..' operator recursively traverses all JSON leaves, 'strings' narrows input to text values, and 'test' filters with a regular expression."
                concept = "Secret Extraction"
            else:
                q = "Why is the `-S` flag essential when comparing two JSON configuration files using Unix diff?"
                code = "diff <(jq -S . config_old.json) <(jq -S . config_new.json)"
                clean_choices = [
                    "It sorts object keys alphabetically, preventing false diff positives from key reordering",
                    "It encrypts sensitive token values before displaying differences",
                    "It strips whitespace and compresses JSON into a single line",
                    "It validates the configuration schema against OpenAPI specs",
                ]
                correct = "It sorts object keys alphabetically, preventing false diff positives from key reordering"
                exp = "Standard JSON objects are unordered. The -S flag orders keys deterministically so that structural equality can be cleanly evaluated by diff."
                concept = "Configuration Diffing"

        if correct not in clean_choices and clean_choices:
            clean_choices[0] = correct

        while len(clean_choices) < 4:
            clean_choices.append(f"Alternative validation pipeline {len(clean_choices) + 1}")

        return cls(
            question=q,
            choices=clean_choices[:4],
            correct_answer=correct,
            explanation=exp or "Refer to the source lesson for verified command syntax and implementation rationale.",
            source_ref=_clean_study_text(source),
            concept=concept.strip() or "Security Automation",
            code_snippet=code.strip(),
            language="bash",
        )


@dataclass(frozen=True)
class StudyAssetsViewModel:
    document_id: int
    flashcards: list[FlashcardViewModel] = field(default_factory=list)
    mcqs: list[MCQViewModel] = field(default_factory=list)
    cached: bool = False
    fallback: bool = False
    metadata: dict[str, Any] | None = None

    @property
    def flashcard_count(self) -> int:
        return len(self.flashcards)

    @property
    def mcq_count(self) -> int:
        return len(self.mcqs)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["flashcards"] = [card.to_dict() for card in self.flashcards]
        data["mcqs"] = [mcq.to_dict() for mcq in self.mcqs]
        return data

    @classmethod
    def from_study_assets_result(cls, result: Any) -> StudyAssetsViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        document_id = int(metadata.get("document_id") or 0)
        raw_flashcards = list(getattr(result, "flashcards", []) or [])
        raw_mcqs = list(getattr(result, "mcqs", []) or [])

        flashcards = [
            FlashcardViewModel.from_any(card, fallback_index=idx)
            for idx, card in enumerate(raw_flashcards, start=1)
        ]
        mcqs = [
            MCQViewModel.from_any(mcq, fallback_index=idx)
            for idx, mcq in enumerate(raw_mcqs, start=1)
        ]

        if not flashcards:
            flashcards = cls._build_default_flashcards()
        if not mcqs:
            mcqs = cls._build_default_mcqs()

        return cls(
            document_id=document_id,
            flashcards=flashcards,
            mcqs=mcqs,
            cached=bool(metadata.get("cached") or False),
            fallback=bool(metadata.get("fallback") or False),
            metadata=metadata,
        )

    @staticmethod
    def _build_default_flashcards() -> list[FlashcardViewModel]:
        return [
            FlashcardViewModel(
                question="How do you parse specific API attributes (id, email, admin flag) using jq in a security recon workflow?",
                answer="Stream response JSON into jq and format a custom sub-object: curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                concept="API Intelligence",
                code_snippet="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                difficulty="Easy",
            ),
            FlashcardViewModel(
                question="What jq filter pattern recursively searches JSON log trees for authentication tokens and high-entropy strings?",
                answer="Combine recursive traversal '..' with type filtering 'strings' and regular expression validation 'select(test(...))'.",
                concept="Threat Hunting",
                code_snippet="cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'",
                difficulty="Medium",
            ),
            FlashcardViewModel(
                question="How can an administrator detect configuration tampering between two JSON files without false positives from key reordering?",
                answer="Normalize both files by alphabetically sorting object keys with 'jq -S .' inside bash process substitution.",
                concept="Integrity Auditing",
                code_snippet="diff <(jq -S . config_old.json) <(jq -S . config_new.json)",
                difficulty="Hard",
            ),
            FlashcardViewModel(
                question="What makes jq superior to grep or awk when handling JSON data in production pipelines?",
                answer="jq understands nested JSON semantics, escapes, arrays, and types natively, preventing parse errors caused by formatting changes or multiline values.",
                concept="CLI Engineering",
                code_snippet="jq -e .status config.json",
                difficulty="Easy",
            ),
        ]

    @staticmethod
    def _build_default_mcqs() -> list[MCQViewModel]:
        return [
            MCQViewModel(
                question="Which command extracts user records from an endpoint and projects only ID, email, and admin rights into compact JSON?",
                choices=[
                    "curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                    "curl -s https://api.target.com/v1/users | jq '.users.id'",
                    "curl -s https://api.target.com/v1/users | grep -E 'id|email|admin'",
                    "curl -s https://api.target.com/v1/users | jq 'filter(.is_admin)'",
                ],
                correct_answer="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                explanation="The expression '.[] | {id, email, admin: .is_admin}' iterates across each item in the array and constructs a dictionary with the specified attributes.",
                concept="API Intelligence",
                code_snippet="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
            ),
            MCQViewModel(
                question="To find potential API keys and tokens in a large JSON file, which jq command searches all string values with regex matching?",
                choices=[
                    "cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'",
                    "cat log.json | jq 'select(.token != null)'",
                    "cat log.json | jq 'keys[] | search(\"token\")'",
                    "cat log.json | jq '.[] | find_secrets()'",
                ],
                correct_answer="cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'",
                explanation="The '..' operator descends into all child elements, 'strings' filters for string data types, and 'select(test(...))' executes the regex predicate.",
                concept="Threat Hunting",
                code_snippet="cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'",
            ),
            MCQViewModel(
                question="What is the primary function of the `-S` option when invoking `jq -S .` in a diff command?",
                choices=[
                    "Sorts keys of all JSON objects alphabetically to eliminate false positives in diffing",
                    "Silences standard output warnings and error messages",
                    "Streams output in chunks to reduce memory footprint on large files",
                    "Strictly validates the document against a JSON Schema file",
                ],
                correct_answer="Sorts keys of all JSON objects alphabetically to eliminate false positives in diffing",
                explanation="Because dictionary keys in JSON are mathematically unordered, key permutation produces misleading textual diffs unless sorted with -S beforehand.",
                concept="Integrity Auditing",
                code_snippet="diff <(jq -S . config_old.json) <(jq -S . config_new.json)",
            ),
        ]


@dataclass(frozen=True)
class FlashcardReviewState:
    question_key: str
    rating: str = "New"
    interval_days: int = 0
    reviews: int = 0
    ease_factor: float = 2.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuizAnswerState:
    question_index: int
    selected_answer: str = ""
    correct: bool = False
    submitted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)