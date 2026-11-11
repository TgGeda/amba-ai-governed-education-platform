from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class GovernanceExecutionContext:
    correlation_id: str
    session_id: str
    principal_id: str
    operation_id: str
    document_id: int | None
    runtime_request_id: str | None
    trace_id: str

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        principal_id: str,
        operation_id: str,
        document_id: int | None = None,
        runtime_request_id: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> "GovernanceExecutionContext":
        def normalized(value: str, name: str) -> str:
            result = str(value).strip()
            if not result:
                raise ValueError(f"{name} must be non-empty")
            return result

        normalized_document_id = None
        if document_id is not None:
            normalized_document_id = int(document_id)
            if normalized_document_id <= 0:
                raise ValueError("document_id must be positive")

        return cls(
            correlation_id=correlation_id
            or f"EDU-CORR-{uuid.uuid4().hex[:20].upper()}",
            session_id=normalized(session_id, "session_id"),
            principal_id=normalized(principal_id, "principal_id"),
            operation_id=normalized(operation_id, "operation_id"),
            document_id=normalized_document_id,
            runtime_request_id=(
                str(runtime_request_id).strip() if runtime_request_id else None
            ),
            trace_id=trace_id or f"EDU-TRACE-{uuid.uuid4().hex[:20].upper()}",
        )

    def bind_document(self, document_id: int) -> "GovernanceExecutionContext":
        normalized = int(document_id)
        if normalized <= 0:
            raise ValueError("document_id must be positive")
        return replace(self, document_id=normalized)

    def bind_runtime_request(self, request_id: str) -> "GovernanceExecutionContext":
        normalized = str(request_id).strip()
        if not normalized:
            raise ValueError("runtime request ID must be non-empty")
        return replace(self, runtime_request_id=normalized)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "GovernanceExecutionContext":
        return cls(
            correlation_id=str(value["correlation_id"]),
            session_id=str(value["session_id"]),
            principal_id=str(value["principal_id"]),
            operation_id=str(value["operation_id"]),
            document_id=(
                int(value["document_id"])
                if value.get("document_id") is not None
                else None
            ),
            runtime_request_id=(
                str(value["runtime_request_id"])
                if value.get("runtime_request_id")
                else None
            ),
            trace_id=str(value["trace_id"]),
        )
