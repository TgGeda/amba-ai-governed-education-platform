from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from amba_ai.logger import logger

_WHISPER_HALLUCINATIONS = {
    "",
    "[blank_audio]",
    "thank you",
    "thanks for watching",
    "subtitles by",
    "subscribe",
    "you",
    "bye",
    "so",
}


def _normalize_transcription(value: str) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .strip(" .,!?:;-")
        .split()
    )


class _VoiceState(Enum):
    IDLE = "idle"
    LISTENING_WAKE = "listening_wake"
    RECORDING_COMMAND = "recording_command"
    PROCESSING = "processing"


@dataclass(frozen=True)
class VoiceServiceConfig:
    wake_word: str = "amba"
    sample_rate: int = 16_000
    max_record_seconds: float = 8.0
    min_record_seconds: float = 0.8
    silence_timeout_seconds: float = 1.2
    energy_threshold: float = 0.015
    wake_threshold: float = 0.45
    wake_cooldown_seconds: float = 1.5
    audio_block_size: int = 1280
    channels: int = 1
    dtype: str = "float32"
    device_index: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VoiceService(QObject):
    wake_word_detected = Signal()
    listening_started = Signal()
    listening_stopped = Signal()
    transcription_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        *,
        wake_word: str = "amba",
        sample_rate: int = 16_000,
        record_seconds: float = 8.0,
        wake_threshold: float = 0.45,
        device_index: Optional[int] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self.config = VoiceServiceConfig(
            wake_word=(wake_word or "amba").lower().strip(),
            sample_rate=max(8_000, int(sample_rate)),
            max_record_seconds=max(2.0, float(record_seconds)),
            wake_threshold=max(0.01, min(float(wake_threshold), 0.99)),
            device_index=device_index,
        )

        self._stream_thread: Optional[_AudioEngineThread] = None

    @property
    def is_running(self) -> bool:
        return bool(self._stream_thread and self._stream_thread.isRunning())

    @Slot()
    def start(self) -> None:
        if self.is_running:
            logger.debug("VoiceService start ignored; stream thread already running")
            return

        self._stream_thread = _AudioEngineThread(config=self.config)
        self._stream_thread.wake_word_detected.connect(self.wake_word_detected)
        self._stream_thread.listening_started.connect(self.listening_started)
        self._stream_thread.listening_stopped.connect(self.listening_stopped)
        self._stream_thread.transcription_ready.connect(self._on_transcription_ready)
        self._stream_thread.error_occurred.connect(self.error_occurred)

        self._stream_thread.start()

        logger.info(
            "VoiceService started",
            extra={
                "context": {
                    "wake_word": self.config.wake_word,
                    "sample_rate": self.config.sample_rate,
                    "max_record_seconds": self.config.max_record_seconds,
                }
            },
        )

    @Slot()
    def stop(self) -> None:
        thread = self._stream_thread
        if thread is None:
            return

        thread.request_stop()

        if not thread.wait(5_000):
            logger.warning("Voice stream did not stop within five seconds")
            thread.requestInterruption()
            thread.wait(1_000)

        if thread.isRunning():
            self.error_occurred.emit("Voice service could not stop cleanly.")
            return

        thread.deleteLater()
        self._stream_thread = None

        logger.info("VoiceService stopped")

    def submit_text_command(self, text: str) -> None:
        clean = str(text or "").strip()
        if clean:
            self.transcription_ready.emit(clean)

    @Slot(str)
    def _on_transcription_ready(self, raw_text: str) -> None:
        clean = " ".join(str(raw_text or "").strip().split())
        normalized = _normalize_transcription(clean)

        if not normalized or normalized in _WHISPER_HALLUCINATIONS:
            logger.debug("Filtered empty or hallucinated transcription: '%s'", clean)
            return

        logger.info("Voice command accepted: '%s'", clean)
        self.transcription_ready.emit(clean)


class _AudioEngineThread(QThread):
    wake_word_detected = Signal()
    listening_started = Signal()
    listening_stopped = Signal()
    transcription_ready = Signal(str)
    transcription_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, *, config: VoiceServiceConfig) -> None:
        super().__init__()
        self.config = config
        self._stop_event = threading.Event()
        self._state = _VoiceState.LISTENING_WAKE
        self._whisper_service: Any | None = None
        self._transcription_thread: Optional[threading.Thread] = None

        self.transcription_finished.connect(self._on_transcription_finished)

    def request_stop(self) -> None:
        self._stop_event.set()
        if self._transcription_thread is not None and self._transcription_thread.is_alive():
            self._transcription_thread.join(timeout=3.0)

    @Slot()
    def _on_transcription_finished(self) -> None:
        if self._stop_event.is_set():
            self._state = _VoiceState.IDLE
            return

        self._state = _VoiceState.LISTENING_WAKE

    def _get_whisper_service(self) -> Any:
        if self._whisper_service is None:
            from amba_ai.compute.edge_whisper import WhisperService

            self._whisper_service = WhisperService()

        return self._whisper_service

    def run(self) -> None:
        try:
            import sounddevice as sd
            from openwakeword.model import Model
        except Exception as exc:
            msg = f"Voice dependencies missing: {exc}. Install sounddevice, numpy, openwakeword."
            logger.warning(msg)
            self.error_occurred.emit(msg)
            return

        try:
            wake_model = self._create_wake_model(Model)
        except Exception as exc:
            logger.exception("Failed to initialize wake-word model")
            self.error_occurred.emit(f"Wake word model error: {exc}")
            return

        audio_queue: queue.Queue[Any] = queue.Queue(maxsize=50)

        def audio_callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status:
                logger.debug("Audio status: %s", status)
            try:
                audio_queue.put_nowait(indata.copy())
            except queue.Full:
                pass

        try:
            stream = sd.InputStream(
                channels=self.config.channels,
                samplerate=self.config.sample_rate,
                blocksize=self.config.audio_block_size,
                device=self.config.device_index,
                callback=audio_callback,
                dtype=self.config.dtype,
            )
        except Exception as exc:
            logger.exception("Failed to open audio input stream")
            self.error_occurred.emit(f"Microphone input stream error: {exc}")
            return

        seconds_per_block = self.config.audio_block_size / self.config.sample_rate
        pre_roll_blocks = max(1, round(0.35 / seconds_per_block))
        pre_roll: deque[Any] = deque(maxlen=pre_roll_blocks)

        calibration_blocks = max(5, int(1.0 / seconds_per_block))
        ambient_energies: list[float] = []
        effective_threshold = self.config.energy_threshold

        speech_buffer: list[Any] = []
        speech_frames_recorded = 0
        silence_counter_seconds = 0.0
        has_detected_speech = False

        with stream:
            logger.info("Unified microphone stream active")

            while not self._stop_event.is_set():
                try:
                    block = audio_queue.get(timeout=0.3)
                except queue.Empty:
                    continue

                flat_audio = np.asarray(block).flatten()

                if len(ambient_energies) < calibration_blocks:
                    ambient_energies.append(float(np.sqrt(np.mean(flat_audio**2))))
                    if len(ambient_energies) == calibration_blocks:
                        ambient_rms = float(np.mean(ambient_energies))
                        effective_threshold = max(self.config.energy_threshold, ambient_rms * 2.5)
                        logger.info("Calibrated ambient energy threshold: %.5f", effective_threshold)
                    continue

                if self._state == _VoiceState.LISTENING_WAKE:
                    pre_roll.append(flat_audio.copy())
                    score = self._predict_wake_score(wake_model, flat_audio)

                    if score >= self.config.wake_threshold:
                        logger.info("Wake word '%s' detected (score=%.3f)", self.config.wake_word, score)

                        if hasattr(wake_model, "reset"):
                            try:
                                wake_model.reset()
                            except Exception:
                                pass

                        self.wake_word_detected.emit()
                        self.listening_started.emit()

                        self._state = _VoiceState.RECORDING_COMMAND
                        speech_buffer = [b.copy() for b in pre_roll]
                        speech_frames_recorded = sum(len(b) for b in speech_buffer)
                        silence_counter_seconds = 0.0
                        has_detected_speech = False

                elif self._state == _VoiceState.RECORDING_COMMAND:
                    speech_buffer.append(flat_audio)
                    speech_frames_recorded += len(flat_audio)
                    recorded_seconds = speech_frames_recorded / self.config.sample_rate

                    energy = float(np.sqrt(np.mean(flat_audio**2)))
                    if energy > effective_threshold:
                        has_detected_speech = True
                        silence_counter_seconds = 0.0
                    else:
                        if has_detected_speech:
                            silence_counter_seconds += seconds_per_block

                    is_silent_stop = (
                        has_detected_speech
                        and recorded_seconds >= self.config.min_record_seconds
                        and silence_counter_seconds >= self.config.silence_timeout_seconds
                    )
                    is_max_timeout = recorded_seconds >= self.config.max_record_seconds

                    if is_max_timeout and not has_detected_speech:
                        logger.info("Voice command timed out without detected speech")
                        self.listening_stopped.emit()
                        self._state = _VoiceState.LISTENING_WAKE
                        speech_buffer = []
                        speech_frames_recorded = 0
                        silence_counter_seconds = 0.0
                        has_detected_speech = False
                        continue

                    if is_silent_stop or is_max_timeout:
                        self.listening_stopped.emit()

                        if not has_detected_speech:
                            self._state = _VoiceState.LISTENING_WAKE
                            speech_buffer = []
                            speech_frames_recorded = 0
                            silence_counter_seconds = 0.0
                            has_detected_speech = False
                            continue

                        self._state = _VoiceState.PROCESSING

                        full_audio = np.concatenate(speech_buffer)
                        speech_buffer = []
                        speech_frames_recorded = 0
                        silence_counter_seconds = 0.0
                        has_detected_speech = False

                        self._transcription_thread = threading.Thread(
                            target=self._transcribe_worker,
                            args=(full_audio,),
                            name="AmbaAI-VoiceTranscription",
                            daemon=True,
                        )
                        self._transcription_thread.start()

    def _predict_wake_score(self, model: Any, audio: Any) -> float:
        prediction = model.predict(audio)
        if not isinstance(prediction, dict):
            return 0.0

        target = self.config.wake_word.lower()

        for key, value in prediction.items():
            normalized_key = str(key).lower()
            if normalized_key == target or target in normalized_key:
                try:
                    return float(value or 0.0)
                except (TypeError, ValueError):
                    return 0.0

        return 0.0

    def _create_wake_model(self, model_cls: Any) -> Any:
        try:
            return model_cls(
                wakeword_models=[self.config.wake_word],
                inference_framework="onnx",
            )
        except Exception as exc:
            msg = f"Specified wake word '{self.config.wake_word}' could not be loaded: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    def _transcribe_worker(self, full_audio: Any) -> None:
        try:
            maximum_samples = int(self.config.sample_rate * self.config.max_record_seconds)
            audio_slice = full_audio[:maximum_samples]
            audio_slice = np.asarray(audio_slice, dtype=np.float32)
            audio_slice = np.nan_to_num(audio_slice, nan=0.0, posinf=0.0, neginf=0.0)

            whisper = self._get_whisper_service()
            text = ""

            if hasattr(whisper, "transcribe_audio_array"):
                text = whisper.transcribe_audio_array(audio_slice, sample_rate=self.config.sample_rate)
            elif hasattr(whisper, "transcribe_array"):
                text = whisper.transcribe_array(audio_slice, sample_rate=self.config.sample_rate)
            elif hasattr(whisper, "transcribe"):
                text = whisper.transcribe(audio_slice)

            clean_text = str(text or "").strip()
            if clean_text:
                self.transcription_ready.emit(clean_text)

        except Exception as exc:
            logger.exception("Voice transcription error")
            self.error_occurred.emit(str(exc))

        finally:
            if not self._stop_event.wait(self.config.wake_cooldown_seconds):
                self.transcription_finished.emit()