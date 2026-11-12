# src/amba_ai/logger.py
from __future__ import annotations

import logging
import json
import gzip
import sys
import traceback
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from amba_ai.config import LOG_PATH, ensure_directories
from amba_ai.exceptions import AmbaAIError


class JsonFormatter(logging.Formatter):
    """Format log records as JSON with contextual metadata and exception tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "function": record.funcName,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            )
            log_entry["exception_message"] = str(record.exc_info[1])
            log_entry["traceback"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_entry["traceback"] = record.exc_text

        extra_context = getattr(record, "context", None)
        if isinstance(extra_context, dict):
            log_entry["context"] = extra_context

        if isinstance(record.msg, AmbaAIError):
            log_entry["error_type"] = type(record.msg).__name__
            log_entry["error_context"] = getattr(record.msg, "context", {})

        return json.dumps(log_entry, ensure_ascii=False)


def compress_old_log(base_filename: Path) -> None:
    """Compress yesterday's log file if it exists and isn't already compressed."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    old_log = base_filename.with_name(f"{base_filename.stem}_{yesterday}.log")
    gz_log = Path(str(old_log) + ".gz")

    if old_log.exists() and not gz_log.exists():
        with open(old_log, "rb") as f_in, gzip.open(gz_log, "wb") as f_out:
            f_out.writelines(f_in)
        old_log.unlink()


def configure_logging(json_format: bool = True, min_level: str = "INFO") -> logging.Logger:
    ensure_directories()

    logger = logging.getLogger("amba_ai")
    logger.setLevel(getattr(logging, min_level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = (
        JsonFormatter()
        if json_format
        else logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(module)s:%(lineno)d | %(message)s"
        )
    )

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    compress_old_log(LOG_PATH)

    return logger


logger = configure_logging()