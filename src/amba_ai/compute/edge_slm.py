from __future__ import annotations

from dataclasses import dataclass, field
import json
import socket
import time
from typing import Any
import urllib.error
import urllib.request

from amba_ai.config import (
    OLLAMA_BASE_URL,
    OLLAMA_DEFAULT_MODEL,
    get_ollama_options,
    resolve_ollama_model_name,
)
from amba_ai.exceptions import ModelUnavailableError
from amba_ai.logger import logger

DEFAULT_SYSTEM_PROMPT = "You are AmbaAI, an offline educational assistant."


@dataclass(frozen=True)
class GenerationResult:
    response_text: str
    model_name: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.response_text


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_DEFAULT_MODEL,
        *,
        healthcheck_timeout_seconds: float = 3.0,
        generation_timeout_seconds: float = 600.0,
        generation_retries: int = 0,
        run_healthcheck_before_generate: bool = True,
        temperature: float | None = None,
        context_length: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = resolve_ollama_model_name(model)
        self.healthcheck_timeout_seconds = healthcheck_timeout_seconds
        self.generation_timeout_seconds = generation_timeout_seconds
        self.generation_retries = generation_retries
        self.run_healthcheck_before_generate = run_healthcheck_before_generate
        self.temperature = temperature
        self.context_length = context_length

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        result = self.generate(prompt=prompt, **kwargs)
        return result.response_text

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> GenerationResult:
        active_model = resolve_ollama_model_name(model or self.model)
        timeout = timeout_seconds or self.generation_timeout_seconds
        retries = self.generation_retries if retry_count is None else retry_count

        self._validate_prompt(prompt)
        self._validate_runtime_values(
            timeout_seconds=timeout,
            retry_count=retries,
        )

        effective_temp = temperature if temperature is not None else self.temperature
        extra = dict(options or {})
        if self.context_length and "num_ctx" not in extra:
            extra["num_ctx"] = self.context_length

        ollama_options = self._build_options(
            temperature=effective_temp,
            max_tokens=max_tokens,
            extra_options=extra,
        )

        if self.run_healthcheck_before_generate:
            self.healthcheck()

        payload = {
            "model": active_model,
            "prompt": prompt,
            "system": system or DEFAULT_SYSTEM_PROMPT,
            "stream": False,
            "options": ollama_options,
        }

        max_attempts = retries + 1
        backoff_seconds = 0.5

        for attempt in range(1, max_attempts + 1):
            context = self._context(
                operation="generate",
                prompt=prompt,
                model=active_model,
                timeout_seconds=timeout,
                retry_count=retries,
                attempt=attempt,
                max_attempts=max_attempts,
                system_prompt_provided=system is not None,
                options=ollama_options,
            )

            logger.info("Ollama generation started", extra={"context": context})
            started_at = time.perf_counter()

            try:
                request = urllib.request.Request(
                    f"{self.base_url}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw_body = response.read().decode("utf-8", errors="replace")

                elapsed_time = round(time.perf_counter() - started_at, 4)
                data = self._decode_response(raw_body, context, elapsed_time)

                response_text = str(data.get("response", "")).strip()
                tokens_used = self._extract_tokens_used(data)

                result = GenerationResult(
                    response_text=response_text,
                    model_name=str(data.get("model") or active_model),
                    tokens_used=tokens_used,
                    metadata={
                        "temperature": ollama_options.get("temperature"),
                        "top_p": ollama_options.get("top_p"),
                        "num_ctx": ollama_options.get("num_ctx"),
                        "num_predict": ollama_options.get("num_predict"),
                        "num_thread": ollama_options.get("num_thread"),
                        "prompt_length": len(prompt),
                        "response_length": len(response_text),
                        "elapsed_time": elapsed_time,
                        "attempt": attempt,
                        "done": data.get("done"),
                        "eval_count": data.get("eval_count"),
                        "prompt_eval_count": data.get("prompt_eval_count"),
                        "total_duration": data.get("total_duration"),
                        "load_duration": data.get("load_duration"),
                        "prompt_eval_duration": data.get("prompt_eval_duration"),
                        "eval_duration": data.get("eval_duration"),
                    },
                )

                logger.info(
                    "Ollama generation succeeded",
                    extra={
                        "context": {
                            **context,
                            "response_length": len(response_text),
                            "tokens_used": tokens_used,
                            "elapsed_time": elapsed_time,
                        }
                    },
                )

                return result

            except urllib.error.HTTPError as exc:
                elapsed_time = round(time.perf_counter() - started_at, 4)
                error_context = {
                    **context,
                    "error_type": "http_error",
                    "status_code": exc.code,
                    "reason": exc.reason,
                    "elapsed_time": elapsed_time,
                    "response_body": self._safe_read_http_error(exc),
                }
                self._log_or_raise_generation_error(
                    "Ollama generation HTTP error",
                    error_context,
                    exc,
                    attempt,
                    max_attempts,
                )

            except urllib.error.URLError as exc:
                elapsed_time = round(time.perf_counter() - started_at, 4)
                error_context = {
                    **context,
                    "error_type": "connection_error",
                    "reason": str(getattr(exc, "reason", exc)),
                    "elapsed_time": elapsed_time,
                }
                self._log_or_raise_generation_error(
                    "Ollama generation connection error",
                    error_context,
                    exc,
                    attempt,
                    max_attempts,
                )

            except socket.timeout as exc:
                elapsed_time = round(time.perf_counter() - started_at, 4)
                error_context = {
                    **context,
                    "error_type": "timeout",
                    "elapsed_time": elapsed_time,
                }
                self._log_or_raise_generation_error(
                    "Ollama generation timed out",
                    error_context,
                    exc,
                    attempt,
                    max_attempts,
                )

            except OSError as exc:
                elapsed_time = round(time.perf_counter() - started_at, 4)
                error_context = {
                    **context,
                    "error_type": "os_error",
                    "error": str(exc),
                    "elapsed_time": elapsed_time,
                }
                self._log_or_raise_generation_error(
                    "Ollama generation failed",
                    error_context,
                    exc,
                    attempt,
                    max_attempts,
                )

            time.sleep(backoff_seconds)
            backoff_seconds *= 2

        self._raise_model_error(
            "Ollama generation failed after retries",
            context=self._context(
                operation="generate",
                prompt=prompt,
                model=active_model,
                timeout_seconds=timeout,
                retry_count=retries,
                max_attempts=max_attempts,
            ),
        )

    def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Iterator[str]:
        active_model = resolve_ollama_model_name(model or self.model)
        options = self._build_options(temperature=temperature, max_tokens=max_tokens, extra_options=None)

        payload = {
            "model": active_model,
            "prompt": prompt,
            "system": system or DEFAULT_SYSTEM_PROMPT,
            "stream": True,
            "options": options,
        }

        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.generation_timeout_seconds) as response:
            for line in response:
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    text = chunk.get("response", "")
                    if text:
                        yield text
                    if chunk.get("done", False):
                        break
                except Exception:
                    continue

    def healthcheck(self) -> bool:
        max_attempts = 2
        backoff_seconds = 0.5

        for attempt in range(1, max_attempts + 1):
            context = self._context(
                operation="healthcheck",
                timeout_seconds=self.healthcheck_timeout_seconds,
                attempt=attempt,
                max_attempts=max_attempts,
            )

            try:
                request = urllib.request.Request(
                    f"{self.base_url}/api/tags",
                    method="GET",
                )

                with urllib.request.urlopen(
                    request,
                    timeout=self.healthcheck_timeout_seconds,
                ) as response:
                    status = getattr(response, "status", None)

                if status == 200:
                    logger.debug("Ollama healthcheck succeeded", extra={"context": context})
                    return True

                error_context = {**context, "status": status}
                if attempt == max_attempts:
                    self._raise_model_error("Ollama healthcheck failed", context=error_context)

            except urllib.error.HTTPError as exc:
                error_context = {
                    **context,
                    "error_type": "http_error",
                    "status_code": exc.code,
                    "reason": exc.reason,
                }
                if attempt == max_attempts:
                    self._raise_model_error("Ollama healthcheck HTTP error", context=error_context, cause=exc)

            except urllib.error.URLError as exc:
                error_context = {
                    **context,
                    "error_type": "connection_error",
                    "reason": str(getattr(exc, "reason", exc)),
                }
                if attempt == max_attempts:
                    self._raise_model_error("Ollama is unavailable", context=error_context, cause=exc)

            except (TimeoutError, socket.timeout) as exc:
                error_context = {"error_type": "timeout"}
                if attempt == max_attempts:
                    self._raise_model_error("Ollama healthcheck timed out", context=error_context, cause=exc)

            except OSError as exc:
                error_context = {"error_type": "os_error", "error": str(exc)}
                if attempt == max_attempts:
                    self._raise_model_error("Ollama healthcheck failed", context=error_context, cause=exc)

            logger.warning("Ollama healthcheck retrying", extra={"context": context})
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

        return False

    def list_models(self) -> list[str]:
        context = self._context(operation="list_models")

        try:
            request = urllib.request.Request(
                f"{self.base_url}/api/tags",
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=self.healthcheck_timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8", errors="replace")

            data = json.loads(raw_body)
            models = data.get("models", [])

            names: list[str] = []
            for item in models:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))

            return names

        except Exception as exc:
            self._raise_model_error(
                "Failed to list Ollama models",
                context={**context, "error": str(exc)},
                cause=exc,
            )

    def model_exists(self, model_name: str) -> bool:
        try:
            return model_name in self.list_models()
        except ModelUnavailableError:
            return False

    def _build_options(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        extra_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        options = get_ollama_options(
            temperature=temperature,
            num_predict=max_tokens,
        )

        if extra_options:
            options.update(extra_options)

        self._validate_generation_options(options)
        return options

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

    @staticmethod
    def _validate_runtime_values(
        *,
        timeout_seconds: float,
        retry_count: int,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if retry_count < 0:
            raise ValueError("retry_count must be greater than or equal to 0")

    @staticmethod
    def _validate_generation_options(options: dict[str, Any]) -> None:
        temperature = float(options.get("temperature", 0.2))
        top_p = float(options.get("top_p", 0.9))
        num_predict = int(options.get("num_predict", 1024))
        num_ctx = int(options.get("num_ctx", 2048))
        num_thread = int(options.get("num_thread", 4))

        if not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")
        if not 0.0 < top_p <= 1.0:
            raise ValueError("top_p must be greater than 0.0 and less than or equal to 1.0")
        if num_predict <= 0:
            raise ValueError("num_predict must be greater than 0")
        if num_ctx <= 0:
            raise ValueError("num_ctx must be greater than 0")
        if num_thread <= 0:
            raise ValueError("num_thread must be greater than 0")

    def _decode_response(
        self,
        raw_body: str,
        context: dict[str, Any],
        elapsed_time: float,
    ) -> dict[str, Any]:
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            self._raise_model_error(
                "Failed to decode Ollama response JSON",
                context={
                    **context,
                    "error_type": "json_decode_error",
                    "elapsed_time": elapsed_time,
                    "raw_response_length": len(raw_body),
                },
                cause=exc,
            )

        if not isinstance(data, dict):
            self._raise_model_error(
                "Unexpected Ollama response type",
                context={
                    **context,
                    "error_type": "invalid_response_type",
                    "elapsed_time": elapsed_time,
                    "response_type": type(data).__name__,
                },
            )

        return data

    def _log_or_raise_generation_error(
        self,
        message: str,
        context: dict[str, Any],
        exc: BaseException,
        attempt: int,
        max_attempts: int,
    ) -> None:
        logger.error(message, extra={"context": context})

        if attempt == max_attempts:
            self._raise_model_error(
                message,
                context=context,
                cause=exc,
            )

    def _context(
        self,
        *,
        operation: str,
        prompt: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "operation": operation,
            "base_url": self.base_url,
            "model": model or self.model,
        }

        if prompt is not None:
            context["prompt_length"] = len(prompt)
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        if retry_count is not None:
            context["retry_count"] = retry_count
        if attempt is not None:
            context["attempt"] = attempt
        if max_attempts is not None:
            context["max_attempts"] = max_attempts

        context.update(extra)
        return context

    def _raise_model_error(
        self,
        message: str,
        *,
        context: dict[str, Any],
        cause: BaseException | None = None,
    ) -> None:
        logger.error(message, extra={"context": context})

        try:
            raise ModelUnavailableError(message, context=context) from cause
        except TypeError:
            enriched = f"{message} | context={json.dumps(context, ensure_ascii=False, default=str)}"
            raise ModelUnavailableError(enriched) from cause

    @staticmethod
    def _safe_read_http_error(exc: urllib.error.HTTPError) -> str | None:
        try:
            body = exc.read()
            if not body:
                return None
            return body.decode("utf-8", errors="replace")[:2000]
        except Exception:
            return None

    @staticmethod
    def _extract_tokens_used(data: dict[str, Any]) -> int | None:
        eval_count = data.get("eval_count")
        prompt_eval_count = data.get("prompt_eval_count")

        if isinstance(eval_count, int) and isinstance(prompt_eval_count, int):
            return eval_count + prompt_eval_count
        if isinstance(eval_count, int):
            return eval_count
        return None