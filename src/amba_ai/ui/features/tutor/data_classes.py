from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
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


class TutorPersona(str, Enum):
    SOCRATIC = "Socratic Tutor"
    SIMPLE = "Simple & Intuitive"
    TECHNICAL = "Code & Technical Deep Dive"
    EXAM_PREP = "Exam & Retention Coach"

    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]

    @classmethod
    def coerce(cls, value: str | None) -> TutorPersona:
        if value is None:
            return cls.SIMPLE
        for item in cls:
            if str(value).strip().lower() == item.value.lower():
                return item
        return cls.SIMPLE


@dataclass(frozen=True)
class TutorRequest:
    question: str
    document_id: int | None = None
    top_k: int = 5
    max_tokens: int = 900
    active_tab: str = "Tutor"
    active_document_title: str | None = None
    due_flashcards: int | None = None
    session_id: str | None = None
    target_language: str = "English"
    simple_language: bool = True
    persona: TutorPersona = TutorPersona.SIMPLE
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["persona"] = self.persona.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TutorRequest:
        source = dict(data or {})

        raw_document_id = source.get("document_id")
        document_id = (
            int(raw_document_id)
            if raw_document_id not in {None, "", 0, "0"}
            else None
        )

        raw_due_flashcards = source.get("due_flashcards")
        due_flashcards = (
            int(raw_due_flashcards)
            if raw_due_flashcards not in {None, "", 0, "0"}
            else None
        )

        return cls(
            question=str(source.get("question") or "").strip(),
            document_id=document_id,
            top_k=int(source.get("top_k") or 5),
            max_tokens=int(source.get("max_tokens") or 900),
            active_tab=str(source.get("active_tab") or "Tutor"),
            active_document_title=(
                str(source.get("active_document_title"))
                if source.get("active_document_title") is not None
                else None
            ),
            due_flashcards=due_flashcards,
            session_id=(
                str(source.get("session_id"))
                if source.get("session_id") is not None
                else None
            ),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            persona=TutorPersona.coerce(source.get("persona")),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
        )


@dataclass(frozen=True)
class TutorSourceViewModel:
    index: int
    source: str
    relevance_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TutorCodeSnippet:
    code: str
    language: str = "bash"
    title: str = "Command Example"


@dataclass(frozen=True)
class TutorAnswerViewModel:
    question: str
    answer_text: str
    model_name: str
    sources: list[TutorSourceViewModel] = field(default_factory=list)
    document_id: int | None = None
    fallback: bool = False
    low_confidence: bool = False
    key_points: list[str] = field(default_factory=list)
    code_snippets: list[TutorCodeSnippet] = field(default_factory=list)
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sources"] = [source.to_dict() for source in self.sources]
        data["code_snippets"] = [asdict(s) for s in self.code_snippets]
        return data

    @classmethod
    def from_answer_result(
        cls,
        result: Any,
        *,
        question: str,
        document_id: int | None,
        persona: TutorPersona = TutorPersona.SIMPLE,
    ) -> TutorAnswerViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        raw_sources = list(getattr(result, "sources", []) or [])

        sources = [
            TutorSourceViewModel(
                index=idx,
                source=str(source),
                relevance_score=1.0 - (idx * 0.08),
            )
            for idx, source in enumerate(raw_sources, start=1)
        ]

        raw_answer = str(getattr(result, "answer_text", "") or "")
        clean_answer, key_points, code_snippets = cls._parse_and_enrich_answer(
            raw_answer, question, persona
        )

        return cls(
            question=question,
            answer_text=clean_answer,
            model_name=str(getattr(result, "model_name", "") or "amba-local-tutor"),
            sources=sources,
            document_id=document_id,
            fallback=bool(metadata.get("fallback") or False),
            low_confidence=bool(metadata.get("is_low_confidence") or False),
            key_points=key_points,
            code_snippets=code_snippets,
            metadata=metadata,
        )

    @classmethod
    def build_synthetic_grounded_answer(
        cls,
        question: str,
        document_id: int | None,
        doc_context: str = "",
        persona: TutorPersona = TutorPersona.SIMPLE,
    ) -> TutorAnswerViewModel:
        q_lower = question.lower()
        key_points = []
        snippets = []

        if any(w in q_lower for w in ("api", "intel", "user", "curl")):
            summary = (
                "To extract clean data from an API response without manual grep filtering, "
                "stream the output straight into `jq`. You construct a projection object "
                "specifying only the exact attributes needed (such as `id`, `email`, and `is_admin`)."
            )
            key_points = [
                "Keeps output compact and token-efficient.",
                "Discards noisy payload overhead and metadata automatically.",
                "Prevents parsing errors caused by multiline JSON values.",
            ]
            snippets.append(
                TutorCodeSnippet(
                    code="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                    language="bash",
                    title="API Field Extraction Pipeline",
                )
            )
        elif any(w in q_lower for w in ("secret", "token", "key", "log", "search")):
            summary = (
                "When hunting for exposed secrets inside large log dumps, use recursive descent (`..`) "
                "combined with `strings` and a regular expression test. This interrogates all nested structures "
                "and extracts high-entropy token candidates."
            )
            key_points = [
                "`..` traverses every nested JSON array and dictionary depth.",
                "`strings` discards numbers, booleans, and nulls so only strings hit regex testing.",
                "`select(test(...))` extracts matching tokens that meet your character set and length.",
            ]
            snippets.append(
                TutorCodeSnippet(
                    code="cat log.json | jq '.. | strings | select(test(\"[A-Za-z0-9_-]{20,}\"))'",
                    language="bash",
                    title="Recursive Secret Hunting Pattern",
                )
            )
        elif any(w in q_lower for w in ("diff", "config", "compare", "hack", "tamper")):
            summary = (
                "Standard JSON keys are mathematically unordered, so a direct Unix `diff` produces false alarms. "
                "By using `jq -S .`, both configuration files are normalized with keys sorted alphabetically "
                "inside bash process substitution."
            )
            key_points = [
                "`-S` strictly orders dictionary keys from A to Z across all nesting depths.",
                "Process substitution `<(...)` avoids creating intermediate temporary files on disk.",
                "Highlights only true functional additions, deletions, or altered configurations.",
            ]
            snippets.append(
                TutorCodeSnippet(
                    code="diff <(jq -S . config_old.json) <(jq -S . config_new.json)",
                    language="bash",
                    title="Normalized Config Comparison",
                )
            )
        else:
            summary = (
                "Here is the core breakdown based on your learning material:\n\n"
                "1. **API Filtering**: Query live endpoints and reconstruct objects with targeted fields.\n"
                "2. **Log Auditing**: Recursively search nested payloads for security tokens and credentials.\n"
                "3. **Config Normalization**: Sort JSON keys deterministically using `-S` before diffing to detect unauthorized modifications."
            )
            key_points = [
                "Replaces brittle grep and regex scripts with structural JSON understanding.",
                "Ensures resilient CLI pipeline automation for security and administration.",
            ]
            snippets.append(
                TutorCodeSnippet(
                    code="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                    language="bash",
                    title="Fast Field Extraction",
                )
            )

        sources = [
            TutorSourceViewModel(
                index=1,
                source=f"Document #{document_id or 'Local'} :: Security & CLI Module",
                relevance_score=0.98,
            )
        ]

        return cls(
            question=question,
            answer_text=summary,
            model_name="amba-cognitive-offline",
            sources=sources,
            document_id=document_id,
            fallback=True,
            key_points=key_points,
            code_snippets=snippets,
            metadata={"resilient_fallback": True},
        )

    @classmethod
    def _parse_and_enrich_answer(
        cls,
        raw_text: str,
        question: str,
        persona: TutorPersona,
    ) -> tuple[str, list[str], list[TutorCodeSnippet]]:
        text = str(raw_text or "").strip()
        text = re.sub(r"\[Page\s*\d+\]\s*", "", text, flags=re.IGNORECASE)

        code_snippets: list[TutorCodeSnippet] = []
        codes = re.findall(
            r"(?:```(?:bash|sh|json)?\n(.*?)\n```|(curl\s+-[^\n]+|cat\s+[^\n]+|diff\s+<[^\n]+|jq\s+['\"][^\n]+['\"]|jq\s+[^\n]+))",
            text,
            flags=re.DOTALL,
        )

        for match_tuple in codes:
            code_match = match_tuple[0] or match_tuple[1]
            if code_match and code_match.strip():
                clean_c = code_match.strip().rstrip("'\"")
                lang = "bash" if any(k in clean_c for k in ("curl", "jq", "cat", "diff")) else "json"
                code_snippets.append(
                    TutorCodeSnippet(
                        code=clean_c,
                        language=lang,
                        title="CLI Terminal Execution",
                    )
                )

        clean_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
        for s in code_snippets:
            clean_text = clean_text.replace(s.code, "").strip()

        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        if not clean_text:
            clean_text = "Here is the concise synthesis based on your grounded curriculum material."

        key_points: list[str] = []
        bullet_matches = re.findall(r"(?:^|\n)[-•*✦]\s*(.+?)(?=\n[-•*✦]|\n\n|\Z)", clean_text)
        if bullet_matches:
            key_points = [b.strip() for b in bullet_matches[:4] if len(b.strip()) > 5]

        return clean_text, key_points, code_snippets