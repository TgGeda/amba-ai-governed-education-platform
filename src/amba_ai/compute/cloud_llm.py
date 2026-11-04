from __future__ import annotations

from dataclasses import dataclass, field
import functools
import json
import mimetypes
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Generator

from amba_ai.config import STUDY_PACKS_DIR
from amba_ai.logger import logger

try:
    from langchain.schema import BaseMessage, HumanMessage, SystemMessage
except Exception:
    BaseMessage = Any
    HumanMessage = None
    SystemMessage = None

try:
    from langchain_openai import ChatOpenAI
except Exception:
    ChatOpenAI = None

try:
    import vertexai
    from langchain_google_vertexai import ChatVertexAI
    from vertexai.generative_models import (
        FunctionDeclaration,
        GenerationConfig,
        GenerativeModel,
        Part,
        SafetySetting,
        Tool as VertexTool,
    )

    try:
        from vertexai.preview.generative_models import GoogleSearchRetrieval
    except Exception:
        GoogleSearchRetrieval = None

    VERTEX_AVAILABLE = True
except Exception:
    vertexai = None
    ChatVertexAI = None
    GenerativeModel = None
    GenerationConfig = None
    SafetySetting = None
    Part = None
    FunctionDeclaration = None
    VertexTool = None
    GoogleSearchRetrieval = None
    VERTEX_AVAILABLE = False


@dataclass(frozen=True)
class CloudGenerationResult:
    response_text: str
    model_name: str
    provider: str | None
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.response_text


def network_retry(
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    jitter: float = 0.5,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempts_left = max(1, int(tries))
            current_delay = max(0.1, float(delay))

            while attempts_left > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    message = str(exc).lower()

                    if "auth" in message or "credential" in message or "permission" in message:
                        raise

                    wait = current_delay + jitter * (2 * (time.time() % 1) - 1)
                    wait = max(0.1, wait)

                    logger.warning(
                        "Cloud LLM call failed; retrying",
                        extra={
                            "context": {
                                "error": str(exc),
                                "wait_seconds": round(wait, 2),
                                "attempts_left": attempts_left - 1,
                            }
                        },
                    )

                    time.sleep(wait)
                    attempts_left -= 1
                    current_delay *= backoff

            return func(*args, **kwargs)

        return wrapper

    return decorator


class CloudLLMProvider:
    DEFAULT_VERTEX_MODEL = "gemini-1.5-flash"
    DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
    DEFAULT_TIMEOUT_SECONDS = 25.0
    MAX_MULTIMODAL_FILE_BYTES = 25 * 1024 * 1024

    def __init__(
        self,
        credentials_path: str | None = None,
        project_id: str | None = None,
        location: str = "us-central1",
        model_name: str = DEFAULT_VERTEX_MODEL,
        temperature: float = 0.2,
        use_grounding: bool = False,
        request_timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.credentials_path = credentials_path
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.temperature = temperature
        self.use_grounding = use_grounding
        self.request_timeout = request_timeout

        self.provider_type: str | None = None
        self._langchain_client: Any | None = None
        self._native_vertex_model: Any | None = None

        self.total_prompt_tokens = 0
        self.total_response_tokens = 0

        self._initialize()

    @property
    def is_available(self) -> bool:
        return self.provider_type is not None and self._langchain_client is not None

    def _initialize(self) -> None:
        if self._try_initialize_vertex():
            return

        if self._try_initialize_openai():
            return

        logger.warning("Cloud LLM disabled. No valid cloud provider configured.")

    def _try_initialize_vertex(self) -> bool:
        if not VERTEX_AVAILABLE:
            return False

        has_credentials = bool(
            self.credentials_path
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or self.project_id
        )

        if not has_credentials:
            return False

        try:
            self._prepare_vertex_credentials()
            vertexai.init(project=self.project_id, location=self.location)

            self._native_vertex_model = self._build_native_vertex_model()
            self._langchain_client = self._build_langchain_vertex_client()
            self.provider_type = "vertex_ai"

            logger.info(
                "Cloud LLM initialized using Vertex AI",
                extra={
                    "context": {
                        "model": self._vertex_model_name(),
                        "location": self.location,
                        "grounding": self.use_grounding,
                    }
                },
            )
            return True

        except Exception as exc:
            logger.warning(
                "Vertex AI initialization failed",
                extra={"context": {"error": str(exc)}},
                exc_info=True,
            )
            self.provider_type = None
            self._native_vertex_model = None
            self._langchain_client = None
            return False

    def _try_initialize_openai(self) -> bool:
        if ChatOpenAI is None:
            return False

        if not os.environ.get("OPENAI_API_KEY"):
            return False

        try:
            self._langchain_client = self._build_openai_client()
            self._native_vertex_model = None
            self.provider_type = "openai"

            logger.info(
                "Cloud LLM initialized using OpenAI",
                extra={"context": {"model": self._openai_model_name()}},
            )
            return True

        except Exception as exc:
            logger.warning(
                "OpenAI initialization failed",
                extra={"context": {"error": str(exc)}},
                exc_info=True,
            )
            self.provider_type = None
            self._langchain_client = None
            return False

    def _prepare_vertex_credentials(self) -> None:
        if self.credentials_path:
            credentials = Path(self.credentials_path).expanduser().resolve()
            if not credentials.exists():
                raise FileNotFoundError(f"Vertex credentials not found: {credentials}")

            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials)

            if not self.project_id:
                try:
                    payload = json.loads(credentials.read_text(encoding="utf-8"))
                    project = payload.get("project_id")
                    if project:
                        self.project_id = str(project)
                except Exception:
                    logger.debug("Could not infer project_id from credentials file", exc_info=True)

        if not self.project_id:
            self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")

    def _vertex_model_name(self) -> str:
        if "gemini" in self.model_name.lower():
            return self.model_name
        return self.DEFAULT_VERTEX_MODEL

    def _openai_model_name(self) -> str:
        if "gpt" in self.model_name.lower():
            return self.model_name
        return self.DEFAULT_OPENAI_MODEL

    def _build_generation_config(self) -> Any:
        return GenerationConfig(
            temperature=self.temperature,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
        )

    def _build_safety_settings(self) -> list[Any]:
        if SafetySetting is None:
            return []

        return [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
        ]

    def _build_vertex_tools(self, *, include_file_tool: bool = True) -> list[Any]:
        if VertexTool is None:
            return []

        tools: list[Any] = []

        if include_file_tool and FunctionDeclaration is not None:
            try:
                save_file = FunctionDeclaration(
                    name="save_study_pack_text",
                    description="Save educational text content into AmbaAI study packs directory.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["filename", "content"],
                    },
                )
                tools.append(VertexTool(function_declarations=[save_file]))
            except Exception:
                logger.debug("Vertex file tool initialization failed", exc_info=True)

        if self.use_grounding and GoogleSearchRetrieval is not None:
            try:
                tools.append(VertexTool.from_google_search_retrieval(GoogleSearchRetrieval()))
            except Exception:
                logger.debug("Vertex grounding tool initialization failed", exc_info=True)

        return tools

    def _build_native_vertex_model(self, system_instruction: str | None = None) -> Any:
        if GenerativeModel is None:
            raise RuntimeError("Vertex AI native SDK is unavailable.")

        return GenerativeModel(
            model_name=self._vertex_model_name(),
            system_instruction=system_instruction,
            generation_config=self._build_generation_config(),
            safety_settings=self._build_safety_settings(),
            tools=self._build_vertex_tools() or None,
        )

    def _build_langchain_vertex_client(self) -> Any:
        if ChatVertexAI is None:
            raise RuntimeError("langchain_google_vertexai is unavailable.")

        kwargs: dict[str, Any] = {
            "model_name": self._vertex_model_name(),
            "temperature": self.temperature,
            "max_output_tokens": 8192,
            "request_timeout": self.request_timeout,
        }

        safety_settings = self._build_safety_settings()
        if safety_settings:
            try:
                kwargs["safety_settings"] = {item.category: item.threshold for item in safety_settings}
            except Exception:
                kwargs["safety_settings"] = safety_settings

        tools = self._build_vertex_tools(include_file_tool=False)
        if tools:
            kwargs["tools"] = tools

        try:
            return ChatVertexAI(**kwargs)
        except TypeError:
            kwargs.pop("tools", None)
            return ChatVertexAI(**kwargs)

    def _build_openai_client(self) -> Any:
        return ChatOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=self._openai_model_name(),
            temperature=self.temperature,
            max_retries=1,
            request_timeout=self.request_timeout,
        )

    @network_retry(exceptions=(Exception,), tries=3, delay=1.0, backoff=2.0, jitter=0.5)
    def invoke(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        as_json: bool = False,
        **kwargs: Any,
    ) -> str:
        if not self.is_available or self._langchain_client is None:
            raise RuntimeError("Cloud LLM is unavailable.")

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        final_prompt = prompt.strip()
        if as_json:
            final_prompt = f"Return strictly valid JSON only.\n\n{final_prompt}"

        messages = self._build_messages(final_prompt, system_prompt)

        logger.debug(
            "Invoking cloud LLM",
            extra={
                "context": {
                    "provider": self.provider_type,
                    "model": self.model_name,
                    "prompt_length": len(final_prompt),
                    "system_prompt": bool(system_prompt),
                }
            },
        )

        response = self._langchain_client.invoke(messages, **kwargs)
        self._track_langchain_usage(response)

        return str(getattr(response, "content", "") or "")

    def safe_invoke(self, *args: Any, **kwargs: Any) -> str | None:
        try:
            return self.invoke(*args, **kwargs)
        except Exception as exc:
            logger.debug(
                "Cloud safe_invoke failed",
                extra={"context": {"error": str(exc)}},
                exc_info=True,
            )
            return None

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> CloudGenerationResult:
        original_temperature = self.temperature
        original_model = self.model_name

        if temperature is not None:
            self.temperature = float(temperature)

        if model:
            self.model_name = model

        try:
            response_text = self.safe_invoke(
                prompt,
                system_prompt=system,
                **kwargs,
            ) or ""

            return CloudGenerationResult(
                response_text=response_text,
                model_name=self.model_name,
                provider=self.provider_type,
                tokens_used=self.total_prompt_tokens + self.total_response_tokens
                if (self.total_prompt_tokens or self.total_response_tokens)
                else None,
                metadata={
                    "provider": self.provider_type,
                    "prompt_length": len(prompt),
                    "response_length": len(response_text),
                    "temperature": self.temperature,
                    "max_tokens": max_tokens,
                },
            )

        finally:
            self.temperature = original_temperature
            self.model_name = original_model

    def stream(
        self,
        parts: list[Any],
        system_prompt: str | None = None,
    ) -> Generator[str, None, str]:
        if self.provider_type != "vertex_ai" or self._native_vertex_model is None:
            raise RuntimeError("Streaming requires Vertex AI configuration.")

        model = (
            self._build_native_vertex_model(system_instruction=system_prompt)
            if system_prompt
            else self._native_vertex_model
        )

        full_response = ""

        try:
            responses = model.generate_content(parts, stream=True)
            for chunk in responses:
                text = getattr(chunk, "text", None)
                if text:
                    full_response += text
                    yield text
                self._track_vertex_usage(chunk)

            return full_response

        except Exception:
            logger.exception("Cloud streaming failed")
            raise

    def build_multimodal_parts(self, text: str, file_paths: list[str]) -> list[Any]:
        parts: list[Any] = [text] if text else []

        if self.provider_type != "vertex_ai" or Part is None:
            return parts

        for path_text in file_paths:
            try:
                path = Path(path_text).expanduser().resolve()
                if not path.exists() or not path.is_file():
                    continue

                if path.stat().st_size > self.MAX_MULTIMODAL_FILE_BYTES:
                    logger.warning(
                        "Skipping large multimodal file",
                        extra={"context": {"path": str(path), "size": path.stat().st_size}},
                    )
                    continue

                mime_type, _ = mimetypes.guess_type(str(path))
                data = path.read_bytes()

                parts.append(
                    Part.from_data(
                        data=data,
                        mime_type=mime_type or "application/octet-stream",
                    )
                )

            except Exception as exc:
                logger.warning(
                    "Failed to attach multimodal file",
                    extra={"context": {"path": path_text, "error": str(exc)}},
                    exc_info=True,
                )

        return parts

    def start_chat(self, system_prompt: str | None = None) -> Any:
        if self.provider_type != "vertex_ai" or self._native_vertex_model is None:
            raise RuntimeError("Native chat sessions require Vertex AI.")

        model = (
            self._build_native_vertex_model(system_instruction=system_prompt)
            if system_prompt
            else self._native_vertex_model
        )

        return model.start_chat(history=[])

    def send_chat(
        self,
        session: Any,
        message: str | list[Any],
        *,
        stream: bool = False,
    ) -> Any:
        try:
            if stream:
                return self._send_chat_stream(session, message)

            response = session.send_message(message)
            self._track_vertex_usage(response)
            return getattr(response, "text", "") or ""

        except Exception:
            logger.exception("Cloud chat turn failed")
            raise

    def _send_chat_stream(
        self,
        session: Any,
        message: str | list[Any],
    ) -> Generator[str, None, str]:
        full_response = ""

        for chunk in session.send_message(message, stream=True):
            text = getattr(chunk, "text", None)
            if text:
                full_response += text
                yield text
            self._track_vertex_usage(chunk)

        return full_response

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        try:
            if tool_name == "save_study_pack_text":
                filename = str(args.get("filename", "")).strip()
                content = str(args.get("content", ""))

                if not filename:
                    return "Tool error: filename is required."

                safe_name = self._safe_filename(filename)
                output_path = (STUDY_PACKS_DIR / safe_name).resolve()
                base_dir = STUDY_PACKS_DIR.resolve()

                if not str(output_path).startswith(str(base_dir)):
                    return "Tool error: invalid output path."

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding="utf-8")

                return f"File saved to {output_path}"

            return f"Unknown tool: {tool_name}"

        except Exception as exc:
            logger.warning(
                "Cloud local tool execution failed",
                extra={"context": {"tool": tool_name, "error": str(exc)}},
                exc_info=True,
            )
            return f"Tool execution failed: {exc}"

    def _build_messages(self, prompt: str, system_prompt: str | None) -> list[Any]:
        if HumanMessage is None or SystemMessage is None:
            raise RuntimeError("LangChain message classes are unavailable.")

        messages: list[Any] = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=prompt))
        return messages

    def _track_vertex_usage(self, response: Any) -> None:
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage is None:
                return

            self.total_prompt_tokens += int(getattr(usage, "prompt_token_count", 0) or 0)
            self.total_response_tokens += int(getattr(usage, "candidates_token_count", 0) or 0)

        except Exception:
            logger.debug("Failed to track Vertex usage", exc_info=True)

    def _track_langchain_usage(self, response: Any) -> None:
        try:
            metadata = getattr(response, "response_metadata", None)
            if not isinstance(metadata, dict):
                return

            token_usage = metadata.get("token_usage") or metadata.get("usage")
            if not isinstance(token_usage, dict):
                return

            self.total_prompt_tokens += int(token_usage.get("prompt_tokens", 0) or 0)
            self.total_response_tokens += int(
                token_usage.get("completion_tokens", token_usage.get("output_tokens", 0)) or 0
            )

        except Exception:
            logger.debug("Failed to track LangChain usage", exc_info=True)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = filename.strip().replace("\\", "/").split("/")[-1]
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)

        if not name:
            name = "study_pack.txt"

        if "." not in name:
            name += ".txt"

        return name[:120]