from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.config import (
    OLLAMA_STRUCTURED_MODEL,
    OLLAMA_SUMMARY_MODEL,
    OLLAMA_TUTOR_MODEL,
    get_model_for_task,
)
from amba_ai.logger import logger


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model_name: str
    context_length: int
    temperature: float


class ModelService:
    """
    Central edge SLM authority for AmbaAI.

    Features:
    - Thread-safe singleton with lazy client pools.
    - Automatic task-to-model routing (Tutor, Summaries, Flashcards, MCQs).
    - Edge SLM health probing with fast timeout checks.
    - Low-latency token streaming support for student UIs.
    - Memory/VRAM conservation via model unloading.
    """

    _instance: Optional["ModelService"] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        *,
        default_model: str = OLLAMA_TUTOR_MODEL,
        temperature: float = 0.2,
        context_length: int = 4096,
    ) -> None:
        self._lock = threading.RLock()
        self._clients: dict[tuple[str, float, int], OllamaClient] = {}
        self._active_model_name = str(default_model)
        self._temperature = float(temperature)
        self._context_length = int(context_length)
        self._last_health_check_time: float = 0.0
        self._is_healthy_cached: bool = False

        logger.info(
            "ModelService initialized",
            extra={
                "context": {
                    "default_model": self._active_model_name,
                    "temperature": self._temperature,
                    "context_length": self._context_length,
                }
            },
        )

    @classmethod
    def get_instance(cls) -> "ModelService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __enter__(self) -> "ModelService":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()

    def get_llm(
        self,
        model_name: str | None = None,
        *,
        temperature: float | None = None,
        context_length: int | None = None,
    ) -> OllamaClient:
        """
        Return an active, thread-safe OllamaClient from the pool.
        """
        target_model = str(model_name or self._active_model_name)
        target_temp = float(self._temperature if temperature is None else temperature)
        target_ctx = int(self._context_length if context_length is None else context_length)

        cache_key = (target_model, target_temp, target_ctx)

        with self._lock:
            client = self._clients.get(cache_key)
            if client is None:
                client = self._create_client(
                    model_name=target_model,
                    temperature=target_temp,
                    context_length=target_ctx,
                )
                self._clients[cache_key] = client
            return client

    def get_client_for_task(
        self,
        task: str,
        *,
        temperature: float | None = None,
        context_length: int | None = None,
    ) -> OllamaClient:
        """
        Resolve the configured model for an educational task and return a client.
        Supported tasks include: tutor_chat, summary, flashcards, mcqs, etc.
        """
        resolved_model = get_model_for_task(task)
        resolved_temp = temperature

        if resolved_temp is None:
            if task in {"flashcards", "mcqs", "structured"}:
                resolved_temp = 0.05
            elif task in {"summary", "notes"}:
                resolved_temp = 0.15
            elif task in {"tutor_chat", "tutor"}:
                resolved_temp = 0.2
            else:
                resolved_temp = self._temperature

        return self.get_llm(
            model_name=resolved_model,
            temperature=resolved_temp,
            context_length=context_length,
        )

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "tutor_chat",
        model_name: str | None = None,
        max_tokens: int = 1200,
        temperature: float | None = None,
    ) -> str:
        """
        Convenience execution helper with automatic model routing.
        """
        if model_name:
            client = self.get_llm(model_name, temperature=temperature)
            target_model = model_name
        else:
            client = self.get_client_for_task(task, temperature=temperature)
            target_model = client.model if hasattr(client, "model") else get_model_for_task(task)

        generation = client.generate(
            prompt=prompt,
            system=system or "",
            model=target_model,
            max_tokens=max_tokens,
            temperature=temperature if temperature is not None else 0.2,
        )

        return str(getattr(generation, "response_text", getattr(generation, "text", generation)))

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "tutor_chat",
        model_name: str | None = None,
        max_tokens: int = 1200,
        temperature: float | None = None,
    ) -> Iterator[str]:
        """
        Stream tokens directly from the edge model for real-time UI typing.
        """
        if model_name:
            client = self.get_llm(model_name, temperature=temperature)
            target_model = model_name
        else:
            client = self.get_client_for_task(task, temperature=temperature)
            target_model = client.model if hasattr(client, "model") else get_model_for_task(task)

        if hasattr(client, "generate_stream"):
            yield from client.generate_stream(
                prompt=prompt,
                system=system or "",
                model=target_model,
                max_tokens=max_tokens,
                temperature=temperature if temperature is not None else 0.2,
            )
        else:
            full_response = self.generate(
                prompt=prompt,
                system=system,
                task=task,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            words = full_response.split(" ")
            for i, word in enumerate(words):
                yield word + (" " if i < len(words) - 1 else "")

    def get_model_info(self) -> ModelInfo:
        with self._lock:
            return ModelInfo(
                provider="ollama",
                model_name=self._active_model_name,
                context_length=self._context_length,
                temperature=self._temperature,
            )

    def set_model(
        self,
        *,
        model_name: str,
        temperature: Optional[float] = None,
        context_length: Optional[int] = None,
    ) -> None:
        """
        Switch the active default model and clear affected cache entries.
        """
        with self._lock:
            self._active_model_name = str(model_name)
            if temperature is not None:
                self._temperature = float(temperature)
            if context_length is not None:
                self._context_length = int(context_length)

            logger.info(
                "Active default model changed",
                extra={
                    "context": {
                        "active_model": self._active_model_name,
                        "temperature": self._temperature,
                        "context_length": self._context_length,
                    }
                },
            )

    def is_healthy(self, force_check: bool = False) -> bool:
        """
        Check if the local Ollama daemon is reachable.
        Caches result for 10 seconds to avoid unnecessary socket polling.
        """
        now = time.time()
        if not force_check and (now - self._last_health_check_time < 10.0):
            return self._is_healthy_cached

        with self._lock:
            try:
                client = self.get_llm()
                if hasattr(client, "health_check"):
                    healthy = bool(client.health_check())
                elif hasattr(client, "list_local_models"):
                    client.list_local_models()
                    healthy = True
                else:
                    healthy = True
            except Exception as exc:
                logger.warning("Local edge SLM health check failed: %s", exc)
                healthy = False

            self._is_healthy_cached = healthy
            self._last_health_check_time = now
            return healthy

    def unload_model(self, model_name: str | None = None) -> bool:
        """
        Unload an edge model from VRAM/RAM (keep_alive=0).
        """
        target = model_name or self._active_model_name
        with self._lock:
            try:
                client = self.get_llm(target)
                if hasattr(client, "unload"):
                    client.unload()
                logger.info("Requested model unload", extra={"context": {"model": target}})
                return True
            except Exception as exc:
                logger.warning("Failed to unload model %s: %s", target, exc)
                return False

    def shutdown(self) -> None:
        """
        Release all pooled LLM client resources and clear caches.
        """
        with self._lock:
            logger.info("Shutting down ModelService client pool")
            for (_, _, _), client in self._clients.items():
                if hasattr(client, "close"):
                    try:
                        client.close()
                    except Exception:
                        pass
            self._clients.clear()

    def _create_client(
        self,
        *,
        model_name: str,
        temperature: float,
        context_length: int,
    ) -> OllamaClient:
        logger.info(
            "Creating pooled OllamaClient",
            extra={
                "context": {
                    "model": model_name,
                    "temperature": temperature,
                    "context_length": context_length,
                }
            },
        )
        try:
            return OllamaClient(
                model=model_name,
                temperature=temperature,
                context_length=context_length,
            )
        except TypeError:
            return OllamaClient(model=model_name)