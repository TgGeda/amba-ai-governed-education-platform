from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from amba_ai.config import DATA_DIR
from amba_ai.logger import logger

OCR_EXE_PATH = DATA_DIR / "bin" / "AmbaOcr" / "AmbaOcr.exe"

class WindowsOcrLoader:
    """Wrapper to call the compiled C# Windows 11 OCR Microservice."""

    def __init__(self, exe_path: Path = OCR_EXE_PATH):
        self.exe_path = exe_path

    def recognize(self, image_path: str, lang_code: str = "en-US", mode: str = "both") -> List[Dict[str, Any]]:
        if not self.exe_path.exists():
            logger.error("AmbaOcr.exe not found.")
            raise FileNotFoundError(f"Missing OCR microservice at {self.exe_path}")

        logger.info(f"Running OCR on {image_path} with lang {lang_code}")

        try:
            result = subprocess.run([str(self.exe_path), image_path, lang_code, mode],
                capture_output=True,
                text=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"OCR Execution failed: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OCR JSON: {e}")
            raise
