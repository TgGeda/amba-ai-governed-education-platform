from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader

from amba_ai.rag.policy_chunk_models import PolicyChunkError
from amba_ai.rag.policy_text_normalizer import PolicyTextNormalizer


@dataclass(frozen=True, slots=True)
class ExtractedPolicyPage:
    page_number: int
    normalized_text: str
    character_count: int

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not isinstance(self.page_number, int):
            raise TypeError("page_number must be an integer")
        if self.page_number < 1:
            raise PolicyChunkError("page_number must be positive")
        if not isinstance(self.normalized_text, str):
            raise TypeError("normalized_text must be a string")
        if isinstance(self.character_count, bool) or not isinstance(self.character_count, int):
            raise TypeError("character_count must be an integer")
        if self.character_count != len(self.normalized_text):
            raise PolicyChunkError("character_count does not match normalized_text")


class PolicyPdfExtractor:
    def __init__(self, normalizer: PolicyTextNormalizer | None = None) -> None:
        self._normalizer = normalizer or PolicyTextNormalizer()

    def extract_pages(
        self,
        pdf_path: Path | str,
        *,
        remove_repeated_marginal_lines: bool = True,
    ) -> tuple[ExtractedPolicyPage, ...]:
        path = Path(pdf_path)
        if path.suffix.lower() != ".pdf":
            raise PolicyChunkError("policy artifact must be a PDF")
        if path.is_symlink():
            raise PolicyChunkError("symlink PDF artifacts are prohibited")
        if not path.is_file():
            raise FileNotFoundError(f"PDF source not found: {path}")
        try:
            reader = PdfReader(str(path))
        except Exception as error:
            raise PolicyChunkError("PDF could not be opened") from error
        if reader.is_encrypted:
            try:
                result = reader.decrypt("")
            except Exception as error:
                raise PolicyChunkError("encrypted PDF could not be decrypted") from error
            if result == 0:
                raise PolicyChunkError("encrypted PDF requires a password")
        raw_pages: list[str] = []
        failures: list[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw_pages.append(page.extract_text() or "")
            except Exception:
                failures.append(page_number)
                raw_pages.append("")
        if failures:
            rendered = ", ".join(str(value) for value in failures)
            raise PolicyChunkError(f"PDF text extraction failed on page(s): {rendered}")
        normalized = tuple(self._normalizer.normalize_page_text(value) for value in raw_pages)
        if remove_repeated_marginal_lines:
            normalized = self._normalizer.remove_repeated_marginal_lines(normalized)
        return tuple(
            ExtractedPolicyPage(
                page_number=index,
                normalized_text=text,
                character_count=len(text),
            )
            for index, text in enumerate(normalized, start=1)
        )
