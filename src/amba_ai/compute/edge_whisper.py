from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Any
import wave

from amba_ai.exceptions import TranscriptionError
from amba_ai.logger import logger

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    whisper = None
    WHISPER_AVAILABLE = False


@dataclass(frozen=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration: float
    model_name: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class EdgeWhisperTranscriber:
    SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".webm", ".mp4", ".mov", ".mkv"}

    def __init__(
        self,
        model_name: str = "small",
        device: str | None = None,
        download_root: str | Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.download_root = str(download_root) if download_root else None
        self._model: Any = None
        self._lock = threading.RLock()

    @property
    def is_available(self) -> bool:
        return WHISPER_AVAILABLE

    def load_model(self) -> Any:
        if not self.is_available:
            raise TranscriptionError(
                "Whisper library is not installed. Please install openai-whisper.",
                context={"model_name": self.model_name},
            )

        with self._lock:
            if self._model is not None:
                return self._model

            try:
                load_kwargs: dict[str, Any] = {}
                if self.device:
                    load_kwargs["device"] = self.device
                if self.download_root:
                    load_kwargs["download_root"] = self.download_root

                logger.info("Loading Whisper model", extra={"context": {"model": self.model_name}})
                self._model = whisper.load_model(self.model_name, **load_kwargs)
                return self._model
            except Exception as exc:
                logger.exception("Failed to load Whisper model")
                raise TranscriptionError(
                    f"Failed to load Whisper model '{self.model_name}': {exc}",
                    context={"model_name": self.model_name, "error": str(exc)},
                ) from exc

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        task: str = "transcribe",
        fp16: bool = False,
        temperature: float = 0.0,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        path = Path(audio_path).expanduser().resolve()
        context = {
            "path": str(path),
            "model_name": self.model_name,
            "language": language,
            "task": task,
        }

        if not path.exists():
            raise TranscriptionError("Audio file not found", context=context)

        if not path.is_file():
            raise TranscriptionError("Audio path is not a file", context=context)

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise TranscriptionError(f"Unsupported audio format: {path.suffix}", context=context)

        model = self.load_model()
        started_at = time.perf_counter()

        try:
            transcribe_kwargs: dict[str, Any] = {
                "task": task,
                "fp16": fp16,
                "temperature": temperature,
            }
            if language:
                transcribe_kwargs["language"] = language
            if initial_prompt:
                transcribe_kwargs["initial_prompt"] = initial_prompt

            result = model.transcribe(str(path), **transcribe_kwargs)
            elapsed_time = round(time.perf_counter() - started_at, 3)

            text = str(result.get("text", "")).strip()
            detected_language = str(result.get("language", language or "unknown"))

            parsed_segments: list[TranscriptionSegment] = []
            for seg in result.get("segments", []):
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", 0.0))
                seg_text = str(seg.get("text", "")).strip()
                parsed_segments.append(
                    TranscriptionSegment(
                        start=round(start, 2),
                        end=round(end, 2),
                        text=seg_text,
                        confidence=float(seg.get("confidence")) if "confidence" in seg else None,
                    )
                )

            duration = 0.0
            if parsed_segments:
                duration = round(parsed_segments[-1].end, 2)
            else:
                wav_duration = self._get_wav_duration(path)
                if wav_duration:
                    duration = wav_duration

            return TranscriptionResult(
                text=text,
                language=detected_language,
                duration=duration,
                model_name=self.model_name,
                segments=parsed_segments,
                metadata={
                    "elapsed_seconds": elapsed_time,
                    "task": task,
                    "file_size_bytes": path.stat().st_size,
                },
            )

        except Exception as exc:
            logger.exception("Whisper transcription failed", extra={"context": context})
            raise TranscriptionError(
                f"Audio transcription failed: {exc}",
                context={**context, "error": str(exc)},
            ) from exc

    @staticmethod
    def _get_wav_duration(path: Path) -> float | None:
        if path.suffix.lower() != ".wav":
            return None
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 2)
        except Exception:
            return None
        return None