from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any
import wave

from docx import Document
from pptx import Presentation
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

from amba_ai.config import (
    FFMPEG_BIN,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_TEXT_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    TEMP_DIR,
    USER_UPLOADS_DIR,
)
from amba_ai.exceptions import IngestionError, TranscriptionError
from amba_ai.logger import logger
from amba_ai.models.schemas import IngestedDocument


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    metadata: dict[str, Any]


def _error_context(
    *,
    path: Path | str | None = None,
    stage: str,
    extension: str | None = None,
    model_name: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    resolved_path = str(path) if path is not None else None
    return {
        "stage": stage,
        "path": resolved_path,
        "extension": extension or (Path(path).suffix.lower() if path else None),
        "model_name": model_name,
        **extra,
    }


def detect_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext == ".pptx":
        return "pptx"
    if ext in SUPPORTED_TEXT_EXTENSIONS or ext in {".txt", ".md"}:
        return "text"
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return "audio"
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def persist_upload(path: Path) -> Path:
    context = _error_context(path=path, stage="persist_upload")
    try:
        USER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        target = USER_UPLOADS_DIR / path.name
        if target.exists():
            stem = path.stem
            suffix = path.suffix
            counter = 1
            while True:
                candidate = USER_UPLOADS_DIR / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1

        shutil.copy2(path, target)
        logger.info(
            "Persisted upload",
            extra={
                "context": {
                    **context,
                    "stored_path": str(target),
                    "size": target.stat().st_size,
                }
            },
        )
        return target
    except OSError as exc:
        raise IngestionError("Failed to persist uploaded file", context=context) from exc


def extract_pdf_text(path: Path) -> ExtractionResult:
    context = _error_context(path=path, stage="extract_pdf_text")
    try:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(f"\n\n[Page {idx}]\n{text}")

        extracted_text = "\n".join(pages).strip()
        page_count = len(reader.pages)
        return ExtractionResult(text=extracted_text, metadata={"page_count": page_count})
    except PdfReadError as exc:
        raise IngestionError("PDF extraction failed", context=context) from exc
    except OSError as exc:
        raise IngestionError("Failed to read PDF file", context=context) from exc


def extract_docx_text(path: Path) -> ExtractionResult:
    context = _error_context(path=path, stage="extract_docx_text")
    try:
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        table_count = 0
        for table in doc.tables:
            table_count += 1
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        extracted_text = "\n".join(parts).strip()
        return ExtractionResult(
            text=extracted_text,
            metadata={"paragraph_count": len(doc.paragraphs), "table_count": table_count},
        )
    except (OSError, ValueError) as exc:
        raise IngestionError("DOCX extraction failed", context=context) from exc


def extract_pptx_text(path: Path) -> ExtractionResult:
    context = _error_context(path=path, stage="extract_pptx_text")
    try:
        presentation = Presentation(str(path))
        slides: list[str] = []
        for idx, slide in enumerate(presentation.slides, start=1):
            slide_text = [f"[Slide {idx}]"]
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text and shape.text.strip():
                    slide_text.append(shape.text.strip())
            slides.append("\n".join(slide_text))

        extracted_text = "\n\n".join(slides).strip()
        return ExtractionResult(text=extracted_text, metadata={"slide_count": len(presentation.slides)})
    except (OSError, ValueError) as exc:
        raise IngestionError("PPTX extraction failed", context=context) from exc


def extract_plain_text(path: Path) -> ExtractionResult:
    context = _error_context(path=path, stage="extract_plain_text")
    try:
        extracted_text = path.read_text(encoding="utf-8", errors="ignore").strip()
        return ExtractionResult(text=extracted_text, metadata={})
    except OSError as exc:
        raise IngestionError("Text extraction failed", context=context) from exc


def validate_whisper_available(*, model_name: str, path: Path | None = None) -> None:
    context = _error_context(path=path, stage="validate_whisper_available", model_name=model_name)
    try:
        import whisper  # noqa: F401
    except ImportError as exc:
        raise TranscriptionError(
            "Whisper is not installed. Install openai-whisper and ensure FFmpeg is available.",
            context=context,
        ) from exc


def get_wav_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate <= 0:
                return None
            return round(frames / float(rate), 3)
    except (wave.Error, OSError):
        return None


def extract_audio_from_video(path: Path) -> ExtractionResult:
    context = _error_context(path=path, stage="extract_audio_from_video")
    try:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise TranscriptionError("Failed to create temporary directory for audio extraction", context=context) from exc

    output = TEMP_DIR / f"{path.stem}.wav"
    cmd = [
        str(FFMPEG_BIN),
        "-y",
        "-i",
        str(path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = get_wav_duration_seconds(output)
        return ExtractionResult(text=str(output), metadata={"audio_path": str(output), "duration": duration})
    except subprocess.CalledProcessError as exc:
        raise TranscriptionError("FFmpeg audio extraction failed", context={**context, "returncode": exc.returncode, "stderr": exc.stderr}) from exc
    except OSError as exc:
        raise TranscriptionError("Failed to execute FFmpeg", context=context) from exc


def transcribe_local_whisper(path: Path, model_name: str = "small") -> ExtractionResult:
    context = _error_context(path=path, stage="transcribe_local_whisper", model_name=model_name)
    validate_whisper_available(model_name=model_name, path=path)

    try:
        import whisper

        model = whisper.load_model(model_name)
        result = model.transcribe(str(path), fp16=False)
        text = str(result.get("text", "")).strip()
        duration = None
        if isinstance(result, dict):
            segments = result.get("segments") or []
            if segments:
                try:
                    duration = round(float(segments[-1].get("end")), 3)
                except (TypeError, ValueError, KeyError):
                    duration = None

        return ExtractionResult(text=text, metadata={"transcription_model": model_name, "duration": duration})
    except TranscriptionError:
        raise
    except RuntimeError as exc:
        raise TranscriptionError("Whisper runtime failure", context=context) from exc
    except OSError as exc:
        raise TranscriptionError("Whisper failed to read media file", context=context) from exc


def ingest_path(path: str | Path, whisper_model: str = "small") -> IngestedDocument:
    source = Path(path).expanduser().resolve()
    context = _error_context(path=source, stage="ingest_path", model_name=whisper_model)

    if not source.exists():
        raise IngestionError("File does not exist", context=context)
    if not source.is_file():
        raise IngestionError("Path is not a file", context=context)

    kind = detect_kind(source)
    if kind == "unknown":
        raise IngestionError("Unsupported file type", context={**context, "extension": source.suffix.lower()})

    persisted = persist_upload(source)
    metadata: dict[str, Any] = {
        "original_path": str(source),
        "stored_path": str(persisted),
        "extension": persisted.suffix.lower(),
        "size": persisted.stat().st_size,
    }

    temp_audio_path: Path | None = None
    try:
        if kind == "pdf":
            result = extract_pdf_text(persisted)
        elif kind == "docx":
            result = extract_docx_text(persisted)
        elif kind == "pptx":
            result = extract_pptx_text(persisted)
        elif kind == "text":
            result = extract_plain_text(persisted)
        elif kind == "audio":
            result = transcribe_local_whisper(persisted, whisper_model)
        elif kind == "video":
            audio_result = extract_audio_from_video(persisted)
            metadata.update(audio_result.metadata)
            temp_audio_path = Path(audio_result.text)
            result = transcribe_local_whisper(temp_audio_path, whisper_model)
        else:
            raise IngestionError("Unsupported kind", context={**context, "kind": kind})

        text = result.text.strip()
        metadata.update(result.metadata)
        if not text:
            raise IngestionError("No text could be extracted from this file", context={**context, "kind": kind, "stored_path": str(persisted)})

        return IngestedDocument(
            title=persisted.stem,
            source_path=str(persisted),
            kind=kind,
            raw_text=text,
            metadata=metadata,
        )
    finally:
        if temp_audio_path is not None:
            try:
                temp_audio_path.unlink(missing_ok=True)
            except OSError:
                pass