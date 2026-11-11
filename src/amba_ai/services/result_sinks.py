from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from amba_ai.governance.runtime.output_guardrails import digest_material
from amba_ai.models.schemas import Flashcard, MCQ


class GovernedDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SinkDeliveryReceipt:
    sink_name: str
    output_id: str
    sanitized_sha256: str
    delivered_at: str
    receipt_id: str
    value: Any = None


class VerifiedSink:
    name = "verified"

    def verify(self, envelope: Any) -> None:
        from amba_ai.services.governed_result_delivery import GovernedResultEnvelope

        if not isinstance(envelope, GovernedResultEnvelope):
            raise TypeError("No sink accepts a raw model response.")
        if digest_material(envelope.sanitized_material) != envelope.sanitized_sha256:
            raise GovernedDeliveryError(f"{self.name} rejected a digest mismatch.")

    def receipt(self, envelope: Any, value: Any = None) -> SinkDeliveryReceipt:
        return SinkDeliveryReceipt(
            sink_name=self.name,
            output_id=envelope.output_id,
            sanitized_sha256=envelope.sanitized_sha256,
            delivered_at=datetime.now(timezone.utc).isoformat(),
            receipt_id="SINK-" + uuid.uuid4().hex[:20].upper(),
            value=value,
        )


class TutorDisplaySink(VerifiedSink):
    name = "tutor_display"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        return self.receipt(envelope, dict(envelope.sanitized_material))


class SummaryPersistenceSink(VerifiedSink):
    name = "summary_persistence"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)

        db = context.get("db")
        if db is None:
            raise GovernedDeliveryError(f"{self.name} requires a database connection.")

        if envelope.document_id is None:
            raise GovernedDeliveryError(f"{self.name} requires an explicit document ID.")

        material = dict(envelope.sanitized_material)
        markdown = material.get("markdown_notes")
        if not isinstance(markdown, str) or not markdown.strip():
            raise GovernedDeliveryError(f"{self.name} requires non-empty markdown_notes.")

        model_name = str(material.get("model_name") or "governed")

        try:
            value = db.insert_summary(
                int(envelope.document_id),
                str(markdown),
                model_name,
            )
        except Exception as exc:
            raise GovernedDeliveryError(
                f"Database summary persistence failed: {type(exc).__name__}: {exc}"
            ) from exc

        return self.receipt(envelope, value)


class NotesPersistenceSink(SummaryPersistenceSink):
    name = "notes_persistence"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)

        db = context.get("db")
        if db is None:
            raise GovernedDeliveryError("Notes persistence requires a database connection.")

        if envelope.document_id is None:
            raise GovernedDeliveryError("Notes persistence requires an explicit document ID.")

        material = dict(envelope.sanitized_material)
        markdown = material.get("markdown_notes")
        if not isinstance(markdown, str) or not markdown.strip():
            raise GovernedDeliveryError("Notes persistence requires non-empty markdown_notes.")

        model_name = str(material.get("model_name") or "governed")

        try:
            value = db.insert_summary(
                int(envelope.document_id),
                str(markdown),
                model_name,
            )
        except Exception as exc:
            raise GovernedDeliveryError(
                f"Database notes persistence failed: {type(exc).__name__}: {exc}"
            ) from exc

        return self.receipt(envelope, value)


class StudyAssetsPersistenceSink(VerifiedSink):
    name = "study_assets_persistence"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)

        db = context.get("db")
        if db is None:
            raise GovernedDeliveryError(f"{self.name} requires a database connection.")

        if envelope.document_id is None:
            raise GovernedDeliveryError(f"{self.name} requires an explicit document ID.")

        material = dict(envelope.sanitized_material)
        cards = [Flashcard(**x) if isinstance(x, dict) else x for x in material.get("flashcards", [])]
        mcqs = [MCQ(**x) if isinstance(x, dict) else x for x in material.get("mcqs", [])]

        try:
            db.insert_flashcards(envelope.document_id, cards)
            db.insert_mcqs(envelope.document_id, mcqs)
        except Exception as exc:
            raise GovernedDeliveryError(
                f"Database study assets persistence failed: {type(exc).__name__}: {exc}"
            ) from exc

        return self.receipt(envelope, {"flashcards": len(cards), "mcqs": len(mcqs)})


class ChatLogSink(VerifiedSink):
    name = "chat_log"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        db = context.get("db")
        if db is None:
            raise GovernedDeliveryError(f"{self.name} requires a database connection.")
        material = dict(envelope.sanitized_material)
        db.log_chat("user", str(context.get("user_text") or ""))
        db.log_chat(
            "assistant",
            str(material.get("answer_text") or ""),
            context=[{"output_id": envelope.output_id, "sanitized_sha256": envelope.sanitized_sha256}],
        )
        return self.receipt(envelope)


class LearningMemorySink(VerifiedSink):
    name = "learning_memory"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        memory = context.get("memory")
        if memory is None:
            raise GovernedDeliveryError(f"{self.name} requires a memory manager instance.")
        material = dict(envelope.sanitized_material)
        value = memory.save_exchange(
            user_text=str(context.get("user_text") or ""),
            assistant_text=str(material.get("answer_text") or ""),
            session_id=str(context.get("session_id") or "default"),
            metadata={
                **dict(context.get("metadata") or {}),
                "output_id": envelope.output_id,
                "sanitized_sha256": envelope.sanitized_sha256,
            },
        )
        return self.receipt(envelope, value)


class ExportSink(VerifiedSink):
    name = "export"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        if "path" not in context or context["path"] is None:
            raise GovernedDeliveryError("Export sink requires a target file path.")
        path = Path(context["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        material = dict(envelope.sanitized_material)
        text = str(material.get("markdown_notes") or material.get("answer_text") or json.dumps(material, ensure_ascii=False, sort_keys=True))
        path.write_text(text, encoding="utf-8")
        return self.receipt(envelope, str(path))


class ClipboardSink(VerifiedSink):
    name = "clipboard"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        material = dict(envelope.sanitized_material)
        text = str(material.get("answer_text") or material.get("markdown_notes") or json.dumps(material, ensure_ascii=False, sort_keys=True))
        writer = context.get("writer")
        if not callable(writer):
            raise GovernedDeliveryError("Clipboard sink requires a controlled writer.")
        writer(text)
        return self.receipt(envelope, text)


class AuditSink(VerifiedSink):
    name = "audit"

    def deliver(self, envelope: Any, **context: Any) -> SinkDeliveryReceipt:
        self.verify(envelope)
        payload = {
            "output_id": envelope.output_id,
            "operation_id": envelope.operation_id,
            "document_id": envelope.document_id,
            "sanitized_sha256": envelope.sanitized_sha256,
            "disposition": getattr(envelope.disposition, "value", str(envelope.disposition)),
            "trace_id": envelope.trace_id,
            "audit_receipt": envelope.audit_receipt,
        }
        writer = context.get("writer")
        if callable(writer):
            writer(payload)
        return self.receipt(envelope, payload)


DEFAULT_SINKS = {
    "tutor_display": TutorDisplaySink(),
    "summary_persistence": SummaryPersistenceSink(),
    "notes_persistence": NotesPersistenceSink(),
    "study_assets_persistence": StudyAssetsPersistenceSink(),
    "chat_log": ChatLogSink(),
    "learning_memory": LearningMemorySink(),
    "export": ExportSink(),
    "clipboard": ClipboardSink(),
    "audit": AuditSink(),
}