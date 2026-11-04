from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from amba_ai.config import STUDY_PACKS_DIR
from amba_ai.core.learning_pack import (
    build_learning_bundle,
    compile_document_agnostic_bundle,
    create_study_guide_pdf,
)
from amba_ai.logger import logger


@dataclass(frozen=True, slots=True)
class StudyPackResult:
    title: str
    pdf_path: str | None
    audio_path: str | None
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetricsProvider(Protocol):
    def increment(self, metric: str, value: int = 1) -> None: ...
    def timing(self, metric: str, milliseconds: float) -> None: ...


class NullMetrics:
    def increment(self, metric: str, value: int = 1) -> None:
        pass

    def timing(self, metric: str, milliseconds: float) -> None:
        pass


class AudioGenerator(Protocol):
    def generate(
        self,
        *,
        text: str,
        output_path: Path,
        rate: int,
    ) -> Path | None: ...


class Pyttsx3AudioGenerator:
    def generate(
        self,
        *,
        text: str,
        output_path: Path,
        rate: int,
    ) -> Path | None:
        try:
            import pyttsx3
        except Exception:
            logger.warning("pyttsx3 unavailable", exc_info=True)
            return None

        tmp_path = _temp_path_for(output_path)

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.save_to_file(text, str(tmp_path))
            engine.runAndWait()

            if not tmp_path.exists():
                raise RuntimeError("Audio file not created")

            if tmp_path.stat().st_size <= 0:
                raise RuntimeError("Audio file is empty")

            tmp_path.replace(output_path)
            return output_path

        except Exception:
            logger.exception("Audio generation failed")
            tmp_path.unlink(missing_ok=True)
            return None


class PDFGenerator(Protocol):
    def generate(
        self,
        *,
        title: str,
        content: str,
        output_path: Path,
    ) -> Path | None: ...


class LearningPackPDFGenerator:
    def generate(
        self,
        *,
        title: str,
        content: str,
        output_path: Path,
    ) -> Path | None:
        return create_study_guide_pdf(
            path=output_path,
            title=title,
            source="AmbaAI Core",
            summary="",
            notes=content,
            flashcards=[],
            mcqs=[],
        )


class StudyPackCompiler:
    MAX_TITLE_CHARS = 300
    MAX_CONTENT_CHARS = 5_000_000
    MAX_TTS_CHARS = 20_000
    DEFAULT_TTS_RATE = 160

    def __init__(
        self,
        output_dir: Path | None = None,
        *,
        pdf_generator: PDFGenerator | None = None,
        audio_generator: AudioGenerator | None = None,
        metrics: MetricsProvider | None = None,
    ) -> None:
        self.output_dir = output_dir or STUDY_PACKS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pdf_generator = pdf_generator or LearningPackPDFGenerator()
        self.audio_generator = audio_generator or Pyttsx3AudioGenerator()
        self.metrics = metrics or NullMetrics()

    def generate_study_pack(
        self,
        title: str,
        content: str,
        *,
        generate_pdf: bool = True,
        generate_audio: bool = True,
    ) -> dict[str, str | None]:
        result = self.compile(
            title=title,
            content=content,
            generate_pdf=generate_pdf,
            generate_audio=generate_audio,
        )
        return {
            "pdf_path": result.pdf_path,
            "audio_path": result.audio_path,
        }

    def compile(
        self,
        title: str,
        content: str,
        *,
        generate_pdf: bool = True,
        generate_audio: bool = True,
    ) -> StudyPackResult:
        started = time.perf_counter()

        clean_title = self._clean_title(title)
        clean_content = self._clean_content(content)

        if not clean_content:
            raise ValueError("Study pack content cannot be empty.")

        safe_name = self._safe_filename(clean_title)
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        pdf_path = self.output_dir / f"{safe_name}_{timestamp}_study_pack.pdf"
        audio_path = self.output_dir / f"{safe_name}_{timestamp}_audio.wav"

        logger.info(
            "Study pack compilation started",
            extra={
                "context": {
                    "title": clean_title,
                    "content_length": len(clean_content),
                }
            },
        )

        final_pdf: Path | None = None
        final_audio: Path | None = None

        if generate_pdf:
            final_pdf = self._execute_pdf_generation(
                clean_title,
                clean_content,
                pdf_path,
            )

        if generate_audio:
            final_audio = self._execute_audio_generation(
                clean_content,
                audio_path,
            )

        duration_ms = (time.perf_counter() - started) * 1000

        result = StudyPackResult(
            title=clean_title,
            pdf_path=str(final_pdf) if final_pdf else None,
            audio_path=str(final_audio) if final_audio else None,
            created_at=time.time(),
            metadata={
                "output_dir": str(self.output_dir),
                "content_length": len(clean_content),
                "pdf_generated": final_pdf is not None,
                "audio_generated": final_audio is not None,
                "offline_only": True,
                "duration_ms": round(duration_ms, 2),
            },
        )

        self.metrics.increment("studypack.success")
        self.metrics.timing("studypack.duration_ms", duration_ms)

        logger.info(
            "Study pack compilation completed",
            extra={"context": result.metadata},
        )

        return result

    def _execute_pdf_generation(
        self,
        title: str,
        content: str,
        output_path: Path,
    ) -> Path | None:
        for attempt in range(3):
            try:
                result = self.pdf_generator.generate(
                    title=title,
                    content=content,
                    output_path=output_path,
                )
                if result:
                    return result
            except Exception:
                logger.exception(
                    "PDF generation attempt failed",
                    extra={"context": {"attempt": attempt + 1}},
                )

        self.metrics.increment("studypack.pdf_failures")
        return None

    def _execute_audio_generation(
        self,
        content: str,
        output_path: Path,
    ) -> Path | None:
        clean_text = self._clean_tts_text(content)
        if not clean_text:
            return None

        clean_text = clean_text[: self.MAX_TTS_CHARS]

        for attempt in range(3):
            try:
                result = self.audio_generator.generate(
                    text=clean_text,
                    output_path=output_path,
                    rate=self.DEFAULT_TTS_RATE,
                )
                if result:
                    return result
            except Exception:
                logger.exception(
                    "Audio generation attempt failed",
                    extra={"context": {"attempt": attempt + 1}},
                )

        self.metrics.increment("studypack.audio_failures")
        return None

    @classmethod
    def compile_professional_bundle(
        cls,
        output_dir: str | Path | None = None,
        *,
        document_id: int,
        title: str,
        source: str,
        summary: str,
        notes: str,
        flashcards: Iterable[Any],
        mcqs: Iterable[Any],
        **kwargs: Any,
    ) -> Any:
        return build_learning_bundle(
            output_dir or STUDY_PACKS_DIR,
            document_id=document_id,
            title=title,
            source=source,
            summary=summary,
            notes=notes,
            flashcards=flashcards,
            mcqs=mcqs,
        )

    @classmethod
    def compile_document_agnostic_bundle(
        cls,
        document: Any,
        **kwargs: Any,
    ) -> Any:
        return compile_document_agnostic_bundle(
            document,
            compiler=cls,
            **kwargs,
        )

    @staticmethod
    def _clean_content(content: str) -> str:
        clean = str(content or "")
        clean = clean.replace("\r\n", "\n").replace("\r", "\n")
        clean = re.sub(r"\n{4,}", "\n\n\n", clean)
        clean = clean.strip()

        if len(clean) > StudyPackCompiler.MAX_CONTENT_CHARS:
            raise ValueError("Content exceeds maximum allowed size")

        return clean

    @staticmethod
    def _clean_title(title: str) -> str:
        clean = " ".join(str(title or "Study Pack").split()).strip()
        clean = clean[: StudyPackCompiler.MAX_TITLE_CHARS]
        return clean or "Study Pack"

    @staticmethod
    def _clean_tts_text(text: str) -> str:
        clean = str(text or "")
        clean = re.sub(r"```[\s\S]*?```", " ", clean)
        clean = re.sub(r"`([^`]*)`", r"\1", clean)
        clean = re.sub(r"[#*_\[\]]+", " ", clean)
        clean = re.sub(r"https?://\S+", " ", clean)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    @staticmethod
    def _safe_filename(title: str) -> str:
        value = title.lower()
        value = re.sub(r"[^a-z0-9\s_-]", "", value)
        value = re.sub(r"\s+", "_", value)
        value = value.strip("_")
        value = value[:80]
        return value or "study_pack"


def _temp_path_for(path: Path) -> Path:
    fd, filename = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=f"{path.suffix}.tmp",
        dir=str(path.parent),
    )

    try:
        os.close(fd)
    except Exception:
        pass

    result = Path(filename)
    result.unlink(missing_ok=True)
    return result