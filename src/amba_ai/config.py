from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Final


def _env_text(name: str, default: str, *, aliases: tuple[str, ...] = ()) -> str:
    for key in (name, *aliases):
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return default


def _env_bool(name: str, default: bool, *, aliases: tuple[str, ...] = ()) -> bool:
    value = _env_text(name, "1" if default else "0", aliases=aliases).lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disabled"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value!r}")


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    aliases: tuple[str, ...] = (),
) -> int:
    raw = _env_text(name, str(default), aliases=aliases)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, received {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}, received {value}")
    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    aliases: tuple[str, ...] = (),
) -> float:
    raw = _env_text(name, str(default), aliases=aliases)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid floating-point value for {name}: {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, received {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}, received {value}")
    return value


def _normalized_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


APP_NAME: Final = "AmbaAI"
APP_VERSION: Final = "1.0.0"
APP_DESCRIPTION: Final = "Offline-first desktop study assistant for ingestion, notes, quizzes, and grounded RAG tutoring."

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DATA_DIR: Final = PROJECT_ROOT / "data"
DB_DIR: Final = DATA_DIR / "db"
SQLITE_PATH: Final = DB_DIR / "amba_ai.sqlite3"
SOVEREIGN_KB_DIR: Final = DATA_DIR / "sovereign_kb"
PERSONAL_KB_DIR: Final = DATA_DIR / "personal_kb"
USER_UPLOADS_DIR: Final = DATA_DIR / "user_uploads"
GOLD_DATASET_DIR: Final = DATA_DIR / "gold_dataset"
STUDY_PACKS_DIR: Final = DATA_DIR / "study_packs"
TEMP_DIR: Final = DATA_DIR / "temp"
LOG_DIR: Final = DATA_DIR / "logs"
LOG_PATH: Final = LOG_DIR / "amba_ai.log"
ASSETS_DIR: Final = PROJECT_ROOT / "assets"
BRANDING_DIR: Final = ASSETS_DIR / "branding"
ICON_ICO_PATH: Final = ASSETS_DIR / "icon.ico"
ICON_ICNS_PATH: Final = ASSETS_DIR / "icon.icns"

_SYSTEM = platform.system().lower()
IS_WINDOWS: Final = _SYSTEM == "windows"
IS_LINUX: Final = _SYSTEM == "linux"
IS_MACOS: Final = _SYSTEM == "darwin"

PYTHON_ENV: Final = _env_text("AMBA_ENV", "production").lower()
DEBUG: Final = _env_bool("AMBA_DEBUG", False)
OFFLINE_FIRST: Final = _env_bool("AMBA_OFFLINE_FIRST", True)
ALLOW_CLOUD_FALLBACK: Final = _env_bool("AMBA_ALLOW_CLOUD_FALLBACK", False)

SUPPORTED_TEXT_EXTENSIONS: Final = frozenset({".pdf", ".docx", ".pptx", ".txt", ".md"})
SUPPORTED_AUDIO_EXTENSIONS: Final = frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"})
SUPPORTED_VIDEO_EXTENSIONS: Final = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi"})
SUPPORTED_EXTENSIONS: Final = SUPPORTED_TEXT_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
MAX_UPLOAD_SIZE_MB: Final = _env_int("AMBA_MAX_UPLOAD_SIZE_MB", 2048, minimum=1, maximum=16384)

DEFAULT_CHUNK_SIZE_CHARS: Final = _env_int("AMBA_CHUNK_SIZE_CHARS", 4200, minimum=800, maximum=8000)
DEFAULT_CHUNK_OVERLAP_CHARS: Final = _env_int("AMBA_CHUNK_OVERLAP_CHARS", 400, minimum=0, maximum=2000)
MIN_CHUNK_SIZE_CHARS: Final = 800
MAX_CHUNK_SIZE_CHARS: Final = 8000
SEMANTIC_CHUNK_TARGET_CHARS: Final = _env_int("AMBA_SEMANTIC_CHUNK_TARGET_CHARS", 1400, minimum=300, maximum=6000)
SEMANTIC_CHUNK_MAX_CHARS: Final = _env_int("AMBA_SEMANTIC_CHUNK_MAX_CHARS", 1900, minimum=500, maximum=8000)
SEMANTIC_CHUNK_OVERLAP_SENTENCES: Final = _env_int("AMBA_SEMANTIC_CHUNK_OVERLAP_SENTENCES", 2, minimum=0, maximum=10)

if DEFAULT_CHUNK_OVERLAP_CHARS >= DEFAULT_CHUNK_SIZE_CHARS:
    raise ValueError("AMBA_CHUNK_OVERLAP_CHARS must be smaller than AMBA_CHUNK_SIZE_CHARS")
if SEMANTIC_CHUNK_MAX_CHARS <= SEMANTIC_CHUNK_TARGET_CHARS:
    raise ValueError("AMBA_SEMANTIC_CHUNK_MAX_CHARS must exceed AMBA_SEMANTIC_CHUNK_TARGET_CHARS")

MIN_FLASHCARDS_PER_SESSION: Final = _env_int("AMBA_MIN_FLASHCARDS", 10, minimum=1, maximum=100)
MAX_FLASHCARDS_PER_SESSION: Final = _env_int("AMBA_MAX_FLASHCARDS", 20, minimum=1, maximum=200)
MIN_MCQS_PER_SESSION: Final = _env_int("AMBA_MIN_MCQS", 5, minimum=1, maximum=100)
MAX_MCQS_PER_SESSION: Final = _env_int("AMBA_MAX_MCQS", 20, minimum=1, maximum=200)

if MIN_FLASHCARDS_PER_SESSION > MAX_FLASHCARDS_PER_SESSION:
    raise ValueError("AMBA_MIN_FLASHCARDS cannot exceed AMBA_MAX_FLASHCARDS")
if MIN_MCQS_PER_SESSION > MAX_MCQS_PER_SESSION:
    raise ValueError("AMBA_MIN_MCQS cannot exceed AMBA_MAX_MCQS")

OLLAMA_BASE_URL: Final = _normalized_url(
    _env_text(
        "AMBA_OLLAMA_BASE_URL",
        "http://127.0.0.1:11500",
        aliases=("OLLAMA_BASE_URL", "OLLAMA_HOST"),
    )
)
DEFAULT_WINDOWS_OLLAMA_EXE: Final = r"F:\Ollama\ollama.exe"
OLLAMA_EXE_PATH: Final = _env_text(
    "AMBA_OLLAMA_EXE",
    DEFAULT_WINDOWS_OLLAMA_EXE if IS_WINDOWS else "ollama",
    aliases=("OLLAMA_EXE",),
)
OLLAMA_MODELS_DIR: Final = Path(
    _env_text(
        "OLLAMA_MODELS",
        r"F:\AmbaAI\ollama_models" if IS_WINDOWS else "~/.ollama/models",
    )
).expanduser()

DEFAULT_LOW_RESOURCE_MODEL: Final = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
OLLAMA_DEFAULT_MODEL: Final = _env_text(
    "AMBA_OLLAMA_MODEL",
    DEFAULT_LOW_RESOURCE_MODEL,
    aliases=("OLLAMA_DEFAULT_MODEL",),
)
OLLAMA_TUTOR_MODEL: Final = _env_text(
    "AMBA_TUTOR_MODEL",
    OLLAMA_DEFAULT_MODEL,
    aliases=("OLLAMA_TUTOR_MODEL",),
)
OLLAMA_SUMMARY_MODEL: Final = _env_text(
    "AMBA_SUMMARY_MODEL",
    OLLAMA_DEFAULT_MODEL,
    aliases=("OLLAMA_SUMMARY_MODEL",),
)
OLLAMA_STRUCTURED_MODEL: Final = _env_text(
    "AMBA_STRUCTURED_MODEL",
    OLLAMA_DEFAULT_MODEL,
    aliases=("OLLAMA_STRUCTURED_MODEL",),
)
OLLAMA_FAST_MODEL: Final = _env_text(
    "AMBA_FAST_MODEL",
    OLLAMA_DEFAULT_MODEL,
    aliases=("OLLAMA_FAST_MODEL",),
)
OLLAMA_REASONING_MODEL: Final = _env_text(
    "AMBA_REASONING_MODEL",
    OLLAMA_DEFAULT_MODEL,
    aliases=("OLLAMA_REASONING_MODEL",),
)
OLLAMA_MODEL: Final = OLLAMA_DEFAULT_MODEL

INSTALLED_OLLAMA_MODELS: Final = {
    "default": OLLAMA_DEFAULT_MODEL,
    "tutor": OLLAMA_TUTOR_MODEL,
    "summary": OLLAMA_SUMMARY_MODEL,
    "structured": OLLAMA_STRUCTURED_MODEL,
    "fast": OLLAMA_FAST_MODEL,
    "reasoning": OLLAMA_REASONING_MODEL,
}

MODEL_TASK_ROUTES: Final = {
    "default": OLLAMA_DEFAULT_MODEL,
    "tutor_chat": OLLAMA_TUTOR_MODEL,
    "rag_answer": OLLAMA_TUTOR_MODEL,
    "notes": OLLAMA_SUMMARY_MODEL,
    "summary": OLLAMA_SUMMARY_MODEL,
    "flashcards": OLLAMA_STRUCTURED_MODEL,
    "mcq": OLLAMA_STRUCTURED_MODEL,
    "quiz": OLLAMA_STRUCTURED_MODEL,
    "json": OLLAMA_STRUCTURED_MODEL,
    "anki_export": OLLAMA_STRUCTURED_MODEL,
    "fast": OLLAMA_FAST_MODEL,
    "preview": OLLAMA_FAST_MODEL,
    "math": OLLAMA_REASONING_MODEL,
    "science_reasoning": OLLAMA_REASONING_MODEL,
    "logic": OLLAMA_REASONING_MODEL,
    "problem_solving": OLLAMA_REASONING_MODEL,
}

OLLAMA_NUM_CTX: Final = _env_int("AMBA_OLLAMA_NUM_CTX", 2048, minimum=512, maximum=32768)
OLLAMA_NUM_PREDICT: Final = _env_int("AMBA_OLLAMA_NUM_PREDICT", 768, minimum=64, maximum=8192)
OLLAMA_TEMPERATURE: Final = _env_float("AMBA_OLLAMA_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0)
OLLAMA_TOP_P: Final = _env_float("AMBA_OLLAMA_TOP_P", 0.9, minimum=0.0, maximum=1.0)
OLLAMA_NUM_THREAD: Final = _env_int("AMBA_OLLAMA_NUM_THREAD", 4, minimum=1, maximum=max(1, os.cpu_count() or 1))
OLLAMA_MAX_LOADED_MODELS: Final = _env_int("AMBA_OLLAMA_MAX_LOADED_MODELS", 1, minimum=1, maximum=8)
OLLAMA_HEALTHCHECK_TIMEOUT_SECONDS: Final = _env_float("AMBA_OLLAMA_HEALTHCHECK_TIMEOUT", 3.0, minimum=0.25, maximum=60.0)
OLLAMA_GENERATION_TIMEOUT_SECONDS: Final = _env_float("AMBA_OLLAMA_GENERATION_TIMEOUT", 600.0, minimum=10.0, maximum=3600.0)
OLLAMA_GENERATION_RETRIES: Final = _env_int("AMBA_OLLAMA_GENERATION_RETRIES", 1, minimum=0, maximum=5)

EMBEDDING_MODEL_NAME: Final = _env_text("AMBA_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_TOP_K: Final = _env_int("AMBA_RAG_TOP_K", 5, minimum=1, maximum=50)
RAG_VECTOR_CANDIDATES: Final = _env_int("AMBA_RAG_VECTOR_CANDIDATES", 20, minimum=1, maximum=200)
RAG_KEYWORD_CANDIDATES: Final = _env_int("AMBA_RAG_KEYWORD_CANDIDATES", 20, minimum=1, maximum=200)
RAG_MIN_SCORE: Final = _env_float("AMBA_RAG_MIN_SCORE", 0.15, minimum=0.0, maximum=1.0)
RAG_MIN_CONFIDENCE: Final = _env_float("AMBA_RAG_MIN_CONFIDENCE", 0.12, minimum=0.0, maximum=1.0)
RAG_CONTEXT_MAX_CHARS: Final = _env_int("AMBA_RAG_CONTEXT_MAX_CHARS", 12000, minimum=1000, maximum=100000)
RAG_ENABLE_HYBRID_SEARCH: Final = _env_bool("AMBA_RAG_ENABLE_HYBRID_SEARCH", True)
RAG_ENABLE_RERANKING: Final = _env_bool("AMBA_RAG_ENABLE_RERANKING", True)
RAG_ENABLE_SOURCE_VERSIONING: Final = _env_bool("AMBA_RAG_ENABLE_SOURCE_VERSIONING", True)
RAG_REQUIRE_ACTIVE_SOURCES: Final = _env_bool("AMBA_RAG_REQUIRE_ACTIVE_SOURCES", True)
FAISS_INDEX_FILENAME: Final = "index.faiss"
FAISS_METADATA_FILENAME: Final = "meta.pkl"
SOURCE_VERSION_MANIFEST_PATH: Final = DB_DIR / "source_versions.json"

WHISPER_MODEL: Final = _env_text("AMBA_WHISPER_MODEL", "small")
FFMPEG_BIN: Final = _env_text("FFMPEG_BIN", "ffmpeg")
AUDIO_SAMPLE_RATE: Final = _env_int("AMBA_AUDIO_SAMPLE_RATE", 16000, minimum=8000, maximum=192000)
AUDIO_CHANNELS: Final = _env_int("AMBA_AUDIO_CHANNELS", 1, minimum=1, maximum=8)

DEFAULT_EXPORT_MARKDOWN: Final = True
DEFAULT_EXPORT_PDF: Final = True
DEFAULT_EXPORT_ANKI_CSV: Final = True
EXPORT_ENCODING: Final = "utf-8"

DEFAULT_LANGUAGE: Final = _env_text("AMBA_DEFAULT_LANGUAGE", "en").lower()
SUPPORTED_UI_LANGUAGES: Final = {
    "en": "English",
    "am": "Amharic",
    "om": "Oromo",
    "so": "Somali",
}

ENABLE_PII_REDACTION: Final = _env_bool("AMBA_ENABLE_PII_REDACTION", True)
ENABLE_AUDIT_LOGGING: Final = _env_bool("AMBA_ENABLE_AUDIT_LOGGING", True)
STORE_RAW_UPLOADS: Final = _env_bool("AMBA_STORE_RAW_UPLOADS", True)


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    max_ram_gb: int = 12
    cpu_class: str = "core-i5-7th-gen"
    gpu_required: bool = False
    chunk_size_chars: int = DEFAULT_CHUNK_SIZE_CHARS
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS
    semantic_chunk_target_chars: int = SEMANTIC_CHUNK_TARGET_CHARS
    semantic_chunk_max_chars: int = SEMANTIC_CHUNK_MAX_CHARS
    max_flashcards: int = MAX_FLASHCARDS_PER_SESSION
    max_mcqs: int = MAX_MCQS_PER_SESSION
    whisper_model: str = WHISPER_MODEL
    default_model: str = OLLAMA_DEFAULT_MODEL
    tutor_model: str = OLLAMA_TUTOR_MODEL
    summary_model: str = OLLAMA_SUMMARY_MODEL
    structured_model: str = OLLAMA_STRUCTURED_MODEL
    fast_model: str = OLLAMA_FAST_MODEL
    reasoning_model: str = OLLAMA_REASONING_MODEL
    ollama_num_ctx: int = OLLAMA_NUM_CTX
    ollama_num_predict: int = OLLAMA_NUM_PREDICT
    ollama_num_thread: int = OLLAMA_NUM_THREAD
    ollama_max_loaded_models: int = OLLAMA_MAX_LOADED_MODELS
    rag_top_k: int = RAG_TOP_K
    rag_context_max_chars: int = RAG_CONTEXT_MAX_CHARS


DEFAULT_HARDWARE_PROFILE: Final = HardwareProfile()


def get_model_for_task(task: str | None = None, fast_mode: bool = False) -> str:
    if fast_mode:
        return OLLAMA_FAST_MODEL
    if not task:
        return OLLAMA_DEFAULT_MODEL
    normalized = task.strip().lower().replace("-", "_").replace(" ", "_")
    return MODEL_TASK_ROUTES.get(normalized, OLLAMA_DEFAULT_MODEL)


def get_ollama_options(
    *,
    temperature: float | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    num_thread: int | None = None,
) -> dict[str, int | float]:
    resolved_temperature = OLLAMA_TEMPERATURE if temperature is None else float(temperature)
    resolved_num_ctx = OLLAMA_NUM_CTX if num_ctx is None else int(num_ctx)
    resolved_num_predict = OLLAMA_NUM_PREDICT if num_predict is None else int(num_predict)
    resolved_num_thread = OLLAMA_NUM_THREAD if num_thread is None else int(num_thread)
    if not 0.0 <= resolved_temperature <= 2.0:
        raise ValueError("temperature must be between 0.0 and 2.0")
    if resolved_num_ctx < 512:
        raise ValueError("num_ctx must be at least 512")
    if resolved_num_predict < 1:
        raise ValueError("num_predict must be positive")
    if resolved_num_thread < 1:
        raise ValueError("num_thread must be positive")
    return {
        "temperature": resolved_temperature,
        "top_p": OLLAMA_TOP_P,
        "num_ctx": resolved_num_ctx,
        "num_predict": resolved_num_predict,
        "num_thread": resolved_num_thread,
    }


def ensure_directories(verbose: bool = False) -> None:
    directories = (
        DATA_DIR,
        DB_DIR,
        SOVEREIGN_KB_DIR,
        PERSONAL_KB_DIR,
        USER_UPLOADS_DIR,
        GOLD_DATASET_DIR,
        STUDY_PACKS_DIR,
        TEMP_DIR,
        LOG_DIR,
        ASSETS_DIR,
        BRANDING_DIR,
    )
    for path in directories:
        path.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"[Config] Directory ready: {path}")
    if not SQLITE_PATH.exists():
        SQLITE_PATH.touch()
        if verbose:
            print(f"[Config] SQLite file created: {SQLITE_PATH}")


def runtime_summary() -> dict[str, str | int | float | bool]:
    return {
        "app": f"{APP_NAME} {APP_VERSION}",
        "environment": PYTHON_ENV,
        "debug": DEBUG,
        "offline_first": OFFLINE_FIRST,
        "cloud_fallback": ALLOW_CLOUD_FALLBACK,
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "sqlite": str(SQLITE_PATH),
        "ollama_base_url": OLLAMA_BASE_URL,
        "ollama_executable": OLLAMA_EXE_PATH,
        "ollama_models_dir": str(OLLAMA_MODELS_DIR),
        "default_model": OLLAMA_DEFAULT_MODEL,
        "tutor_model": OLLAMA_TUTOR_MODEL,
        "summary_model": OLLAMA_SUMMARY_MODEL,
        "structured_model": OLLAMA_STRUCTURED_MODEL,
        "fast_model": OLLAMA_FAST_MODEL,
        "reasoning_model": OLLAMA_REASONING_MODEL,
        "ollama_num_ctx": OLLAMA_NUM_CTX,
        "ollama_num_predict": OLLAMA_NUM_PREDICT,
        "ollama_num_thread": OLLAMA_NUM_THREAD,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "rag_top_k": RAG_TOP_K,
        "rag_min_confidence": RAG_MIN_CONFIDENCE,
        "whisper_model": WHISPER_MODEL,
    }


def print_runtime_summary() -> None:
    for key, value in runtime_summary().items():
        print(f"{key}: {value}")


AMBAAI_MODEL_ALIASES = {
    "ambaai-cpu": OLLAMA_DEFAULT_MODEL,
    "ambaai": OLLAMA_DEFAULT_MODEL,
    "default": OLLAMA_DEFAULT_MODEL,
}

def resolve_ollama_model_name(model_name: str | None = None) -> str:
    candidate = str(model_name or OLLAMA_DEFAULT_MODEL).strip()
    if not candidate:
        return OLLAMA_DEFAULT_MODEL
    return AMBAAI_MODEL_ALIASES.get(candidate.lower(), candidate)
