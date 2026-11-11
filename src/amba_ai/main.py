from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _bootstrap_src_path() -> None:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    src_dir = package_dir.parent
    project_root = src_dir.parent

    candidates = [
        src_dir,
        project_root / "src",
    ]

    for candidate in candidates:
        if (candidate / "amba_ai").exists():
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)


_bootstrap_src_path()

from amba_ai.config import ensure_directories
from amba_ai.logger import logger


APP_NAME = "AmbaAI"
APP_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_STARTUP_ERROR = 1
EXIT_QT_ERROR = 2
EXIT_HEADLESS_ERROR = 3


@dataclass(frozen=True)
class CliArgs:
    debug: bool = False
    config: Path | None = None
    headless: bool = False
    no_splash: bool = False
    style: Path | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> CliArgs:
    parser = argparse.ArgumentParser(
        prog="amba-ai",
        description="AmbaAI Offline Study Assistant",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose/debug startup logging.",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional alternate config file path.",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run startup checks without launching the UI.",
    )

    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Reserved for packaged builds. Currently no-op.",
    )

    parser.add_argument(
        "--style",
        type=Path,
        default=None,
        help="Optional QSS stylesheet path.",
    )

    parsed = parser.parse_args(argv)

    return CliArgs(
        debug=bool(parsed.debug),
        config=parsed.config,
        headless=bool(parsed.headless),
        no_splash=bool(parsed.no_splash),
        style=parsed.style,
    )


def _context(
    *,
    operation: str,
    args: CliArgs | None = None,
    **extra: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "operation": operation,
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "timestamp": _now_iso(),
        "platform": platform.platform(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
        "sys_path_head": sys.path[:5],
    }

    if args is not None:
        context.update(
            {
                "debug": args.debug,
                "headless": args.headless,
                "config": str(args.config) if args.config else None,
                "no_splash": args.no_splash,
                "style": str(args.style) if args.style else None,
            }
        )

    context.update(extra)
    return context


def configure_runtime(args: CliArgs) -> None:
    context = _context(operation="configure_runtime", args=args)

    if args.debug:
        os.environ["AMBA_DEBUG"] = "1"
        logger.info("Debug mode enabled", extra={"context": context})

    if args.config is not None:
        config_path = args.config.expanduser().resolve()

        if not config_path.exists():
            raise FileNotFoundError(f"Config file does not exist: {config_path}")

        os.environ["AMBA_AI_CONFIG_PATH"] = str(config_path)

        logger.info(
            "Alternate config file selected",
            extra={"context": {**context, "config_path": str(config_path)}},
        )


def validate_python_version() -> None:
    context = _context(operation="validate_python_version")

    if sys.version_info < (3, 10):
        raise RuntimeError(
            "AmbaAI requires Python 3.10 or newer. "
            f"Current version: {platform.python_version()}"
        )

    logger.info(
        "Python version validated",
        extra={
            "context": {
                **context,
                "python_version_short": platform.python_version(),
            }
        },
    )


def validate_pyside6_available() -> None:
    context = _context(operation="validate_pyside6_available")

    spec = importlib.util.find_spec("PySide6")
    if spec is None:
        raise RuntimeError(
            "PySide6 is not installed. Install PySide6 before launching the UI."
        )

    logger.info("PySide6 availability validated", extra={"context": context})


def collect_compute_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "torch_available": False,
        "cuda_available": False,
        "cuda_device_count": 0,
    }

    try:
        torch_spec = importlib.util.find_spec("torch")
        if torch_spec is None:
            return info

        import torch  # type: ignore

        info["torch_available"] = True
        info["cuda_available"] = bool(torch.cuda.is_available())
        info["cuda_device_count"] = int(torch.cuda.device_count())

        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            info["cuda_device_name"] = torch.cuda.get_device_name(0)

    except Exception as exc:
        info["compute_info_error"] = str(exc)

    return info


def collect_optional_dependency_info() -> dict[str, bool]:
    optional_modules = [
        "faiss",
        "sentence_transformers",
        "sounddevice",
        "openwakeword",
        "PySide6.QtCharts",
        "reportlab",
        "pyttsx3",
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_openai",
        "sumy",
        "nltk",
    ]

    availability: dict[str, bool] = {}

    for module_name in optional_modules:
        try:
            availability[module_name] = importlib.util.find_spec(module_name) is not None
        except Exception:
            availability[module_name] = False

    return availability


def validate_startup(args: CliArgs) -> dict[str, Any]:
    context = _context(operation="validate_startup", args=args)

    logger.info("Startup validation started", extra={"context": context})

    configure_runtime(args)
    validate_python_version()

    if not args.headless:
        validate_pyside6_available()

    try:
        ensure_directories()
    except Exception as exc:
        logger.exception(
            "Directory validation failed",
            extra={
                "context": {
                    **context,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        raise RuntimeError("Failed to validate or create required directories.") from exc

    startup_metadata = {
        "directories_validated": True,
        "compute": collect_compute_info(),
        "optional_dependencies": collect_optional_dependency_info(),
    }

    logger.info(
        "Startup validation completed",
        extra={"context": {**context, **startup_metadata}},
    )

    return startup_metadata


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    src_dir = package_dir.parent
    return src_dir.parent


def _default_qss_candidates() -> list[Path]:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    root = _project_root()

    return [
        package_dir / "ui" / "styles" / "amba_ai.qss",
        root / "src" / "amba_ai" / "ui" / "styles" / "amba_ai.qss",
        Path.cwd() / "src" / "amba_ai" / "ui" / "styles" / "amba_ai.qss",
        Path.cwd() / "amba_ai.qss",
    ]


def resolve_stylesheet_path(args: CliArgs) -> Path | None:
    if args.style is not None:
        path = args.style.expanduser().resolve()
        return path if path.exists() and path.is_file() else None

    env_style = os.environ.get("AMBA_AI_QSS_PATH")
    if env_style:
        path = Path(env_style).expanduser().resolve()
        if path.exists() and path.is_file():
            return path

    for candidate in _default_qss_candidates():
        try:
            resolved = candidate.expanduser().resolve()
            if resolved.exists() and resolved.is_file():
                return resolved
        except Exception:
            continue

    return None


def apply_stylesheet(app: Any, args: CliArgs) -> None:
    context = _context(operation="apply_stylesheet", args=args)

    try:
        qss_path = resolve_stylesheet_path(args)

        if qss_path is None:
            logger.warning(
                "QSS stylesheet not found; using default Qt style",
                extra={"context": context},
            )
            return

        qss_text = qss_path.read_text(encoding="utf-8")

        if not qss_text.strip():
            logger.warning(
                "QSS stylesheet is empty; using default Qt style",
                extra={"context": {**context, "qss_path": str(qss_path)}},
            )
            return

        app.setStyleSheet(qss_text)

        logger.info(
            "QSS stylesheet applied",
            extra={
                "context": {
                    **context,
                    "qss_path": str(qss_path),
                    "qss_length": len(qss_text),
                }
            },
        )

    except Exception as exc:
        logger.warning(
            "Failed to apply QSS stylesheet",
            extra={
                "context": {
                    **context,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
            exc_info=True,
        )


def configure_qt_runtime() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


def run_headless(args: CliArgs) -> int:
    context = _context(operation="run_headless", args=args)

    try:
        validate_startup(args)

        logger.info(
            "Headless startup validation completed successfully",
            extra={"context": context},
        )

        return EXIT_OK

    except Exception as exc:
        logger.exception(
            "Headless startup validation failed",
            extra={
                "context": {
                    **context,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        traceback.print_exc()
        return EXIT_HEADLESS_ERROR


def _print_startup_failure(exc: BaseException) -> None:
    print("\n========== AMBAAI STARTUP FAILURE ==========", file=sys.stderr)
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    print("--------------------------------------------", file=sys.stderr)
    traceback.print_exc()
    print("============================================\n", file=sys.stderr)


def run_app(args: CliArgs) -> int:
    context = _context(operation="run_app", args=args)

    try:
        configure_qt_runtime()
        validate_startup(args)

        logger.info("Importing QApplication and MainWindow", extra={"context": context})

        from PySide6.QtWidgets import QApplication
        from amba_ai.ui.main_window import MainWindow
        from amba_ai.application.bootstrap import create_desktop_services

        logger.info("Creating QApplication", extra={"context": context})

        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName("AmbaAI")
        app.setOrganizationDomain("amba-ai.local")

        apply_stylesheet(app, args)

        logger.info("Creating main window", extra={"context": context})

        bootstrap = create_desktop_services(project_root=_project_root())
        bootstrap.application.start()
        window = MainWindow(bootstrap.services)
        app.aboutToQuit.connect(bootstrap.close)
        window.show()

        logger.info("Main window created successfully", extra={"context": context})

        exit_code = int(app.exec())

        logger.info(
            "Application exited",
            extra={"context": {**context, "exit_code": exit_code}},
        )

        return exit_code

    except ImportError as exc:
        logger.exception(
            "Application failed to start due to import error",
            extra={
                "context": {
                    **context,
                    "error_type": "import_error",
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        _print_startup_failure(exc)
        return EXIT_QT_ERROR

    except RuntimeError as exc:
        logger.exception(
            "Application failed to start due to runtime error",
            extra={
                "context": {
                    **context,
                    "error_type": "runtime_error",
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        _print_startup_failure(exc)
        return EXIT_STARTUP_ERROR

    except Exception as exc:
        logger.exception(
            "Fatal application startup failure",
            extra={
                "context": {
                    **context,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        _print_startup_failure(exc)
        return EXIT_STARTUP_ERROR


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logger.info(
        "Starting AmbaAI",
        extra={"context": _context(operation="main", args=args)},
    )

    exit_code = run_headless(args) if args.headless else run_app(args)

    logger.info(
        "AmbaAI shutdown complete",
        extra={
            "context": {
                **_context(operation="main_exit", args=args),
                "exit_code": exit_code,
            }
        },
    )

    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())