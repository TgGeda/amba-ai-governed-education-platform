from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .models import RuntimeGovernanceGateError, RuntimeGovernanceReviewRequired


class OutputDisposition(str, Enum):
    DISPLAY = "display"
    DISPLAY_WITH_WARNING = "display_with_warning"
    REDACT_AND_DISPLAY = "redact_and_display"
    REGENERATE = "regenerate"
    REQUIRE_TEACHER_REVIEW = "require_teacher_review"
    REFUSE = "refuse"


@dataclass(frozen=True)
class GovernedOutputValidation:
    output_id: str
    document_id: int
    operation: str
    decision: OutputDisposition
    sanitized_material: dict[str, Any]
    raw_output_sha256: str
    sanitized_output_sha256: str
    source_digest_verified: bool
    retrieved_chunk_ids: tuple[int, ...]
    excluded_chunk_ids: tuple[int, ...]
    grounding_status: str
    unsupported_claims: tuple[str, ...]
    citation_status: str
    privacy_redactions: tuple[str, ...]
    sensitive_child_data: bool
    assessment_integrity_status: str
    harm_status: str
    age_suitability: str
    prompt_leakage_status: str
    commercial_influence_status: str
    display_status: str
    trace_id: str
    audit_receipt: str

    def __str__(self) -> str:
        """Return the audit receipt for legacy string consumers."""
        return self.audit_receipt

    def startswith(
        self,
        prefix: str | tuple[str, ...],
        *args: int,
    ) -> bool:
        """Support legacy receipt-prefix checks."""
        return self.audit_receipt.startswith(prefix, *args)

    def evidence(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "document_id": self.document_id,
            "operation": self.operation,
            "decision": self.decision.value,
            "source_digest_verified": self.source_digest_verified,
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
            "excluded_chunk_ids": list(self.excluded_chunk_ids),
            "grounding_status": self.grounding_status,
            "unsupported_claims": list(self.unsupported_claims),
            "citation_status": self.citation_status,
            "privacy_redactions": list(self.privacy_redactions),
            "sensitive_child_data": self.sensitive_child_data,
            "assessment_integrity_status": self.assessment_integrity_status,
            "harm_status": self.harm_status,
            "age_suitability": self.age_suitability,
            "prompt_leakage_status": self.prompt_leakage_status,
            "commercial_influence_status": self.commercial_influence_status,
            "display_status": self.display_status,
            "trace_id": self.trace_id,
            "audit_receipt": self.audit_receipt,
        }


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"\b(?:\+?251|0)9\d{8}\b")
_STUDENT_ID = re.compile(r"\bstudent\s*(?:id|number)\s*[:#]?\s*[A-Z0-9-]{3,}\b", re.I)
_LOCAL_PATH = re.compile(r"\b[A-Z]:\\(?:[^\s<>:\"/\\|?*]+\\)*[^\s<>:\"/\\|?*]*", re.I)
_PROMPT_LEAK = re.compile(
    r"(?i)(?:system\s+prompt|developer\s+(?:message|instructions?)|"
    r"ignore\s+(?:all\s+)?previous\s+instructions|hidden\s+policy|"
    r"BEGIN\s+(?:SYSTEM|DEVELOPER)\s+MESSAGE)"
)
_COMMERCIAL = re.compile(
    r"(?i)(?:targeted\s+advertis|send\s+(?:the\s+)?learner\s+profile|"
    r"buy\s+now|limited\s+time\s+offer|sponsored\s+recommendation|"
    r"based\s+on\s+your\s+(?:private|sensitive)\s+(?:profile|data))"
)
_ASSESSMENT = re.compile(
    r"(?i)(?:final\s+exam\s+answer\s+key|protected\s+answer\s+key|"
    r"confidential\s+marking\s+scheme|active\s+graded\s+assessment\s+answers?)"
)
_HARM = re.compile(
    r"(?i)(?:step[- ]by[- ]step\s+(?:suicide|self[- ]harm)|"
    r"instructions?\s+to\s+(?:build\s+(?:a\s+)?bomb|poison\s+someone)|"
    r"sexual\s+exploitation\s+instructions?)"
)
_SENSITIVE_CHILD = re.compile(
    r"(?i)(?:minor|child|student).{0,30}(?:medical\s+record|diagnosis|"
    r"disability|disciplinary\s+record|family\s+case|abuse\s+report)"
)
_CLAIM_CUE = re.compile(r"(?i)\b(always|never|proves?|guarantees?|definitively|100%)\b")
_CHUNK_CITATION = re.compile(r"(?i)\bchunk(?:_id)?\s*[:#]?\s*(\d+)\b")


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_material(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _redact_text(text: str) -> tuple[str, list[str]]:
    redactions: list[str] = []
    value = text
    for label, pattern, replacement in (
        ("email", _EMAIL, "[REDACTED EMAIL]"),
        ("phone", _PHONE, "[REDACTED PHONE]"),
        ("student_identifier", _STUDENT_ID, "[REDACTED STUDENT IDENTIFIER]"),
        ("local_path", _LOCAL_PATH, "[REDACTED LOCAL PATH]"),
    ):
        count = len(pattern.findall(value))
        if count:
            value = pattern.sub(replacement, value)
            redactions.extend([label] * count)
    return value, redactions


def sanitize_structure(value: Any) -> tuple[Any, list[str]]:
    redactions: list[str] = []
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            sanitized, child_redactions = sanitize_structure(item)
            result[str(key)] = sanitized
            redactions.extend(child_redactions)
        return result, redactions
    if isinstance(value, tuple):
        items = []
        for item in value:
            sanitized, child_redactions = sanitize_structure(item)
            items.append(sanitized)
            redactions.extend(child_redactions)
        return tuple(items), redactions
    if isinstance(value, list):
        items = []
        for item in value:
            sanitized, child_redactions = sanitize_structure(item)
            items.append(sanitized)
            redactions.extend(child_redactions)
        return items, redactions
    return value, redactions


def inspect_output_text(
    text: str,
    *,
    operation: str,
    excluded_chunk_ids: set[int],
) -> dict[str, Any]:
    cited_ids = {int(value) for value in _CHUNK_CITATION.findall(text)}
    prohibited_citations = sorted(cited_ids.intersection(excluded_chunk_ids))
    prompt_leak = bool(_PROMPT_LEAK.search(text))
    commercial = bool(_COMMERCIAL.search(text))
    assessment = bool(_ASSESSMENT.search(text))
    harm = bool(_HARM.search(text))
    sensitive_child = bool(_SENSITIVE_CHILD.search(text))
    unsupported = tuple(sorted({match.group(0) for match in _CLAIM_CUE.finditer(text)}))

    if prompt_leak:
        raise RuntimeGovernanceGateError("Output refused: privileged prompt or policy leakage detected.")
    if commercial:
        raise RuntimeGovernanceGateError("Output refused: commercial manipulation or learner profiling detected.")
    if harm:
        raise RuntimeGovernanceGateError("Output refused: actionable harmful instructions detected.")
    if prohibited_citations:
        raise RuntimeGovernanceGateError(
            "Output refused: excluded governance chunks were cited: "
            + ", ".join(str(value) for value in prohibited_citations)
        )
    if assessment:
        raise RuntimeGovernanceReviewRequired(
            f"Output requires authorized teacher review for protected assessment material ({operation})."
        )
    if sensitive_child:
        raise RuntimeGovernanceReviewRequired(
            f"Output requires authorized review for sensitive child data ({operation})."
        )

    return {
        "cited_chunk_ids": tuple(sorted(cited_ids)),
        "unsupported_claims": unsupported,
        "prompt_leakage_status": "passed",
        "commercial_influence_status": "passed",
        "assessment_integrity_status": "passed",
        "harm_status": "passed",
        "sensitive_child_data": False,
    }
