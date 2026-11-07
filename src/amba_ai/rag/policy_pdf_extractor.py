from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from pypdf import PdfReader

from amba_ai.rag.policy_chunk_models import PolicyChunkError
from amba_ai.rag.policy_text_normalizer import PolicyTextNormalizer


class PdfExtractionProfile(str, Enum):
    STANDARD = "standard"
    ETHIOPIAN_BILINGUAL_COLUMNS_V1 = "ethiopian_bilingual_columns_v1"


def _matrix_position(cm: Sequence[float], tm: Sequence[float]) -> tuple[float, float]:
    if len(cm) < 6 or len(tm) < 6:
        raise PolicyChunkError("PDF text matrix is incomplete")
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    return float(x), float(y)


@dataclass(frozen=True, slots=True)
class ExtractedPolicyPage:
    page_number: int
    normalized_text: str
    character_count: int
    language: str | None = None
    column: str | None = None
    parallel_unit_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not isinstance(self.page_number, int):
            raise TypeError("page_number must be an integer")
        if self.page_number < 1:
            raise PolicyChunkError("page_number must be positive")
        if not isinstance(self.normalized_text, str):
            raise TypeError("normalized_text must be a string")
        if not self.normalized_text.strip():
            raise PolicyChunkError("normalized_text must not be empty or whitespace only")
        if isinstance(self.character_count, bool) or not isinstance(self.character_count, int):
            raise TypeError("character_count must be an integer")
        if self.character_count != len(self.normalized_text):
            raise PolicyChunkError("character_count does not match normalized_text")
        if (self.language is None) != (self.column is None):
            raise PolicyChunkError("language and column must both be set or both be None")
        if self.language is not None:
            if not isinstance(self.language, str):
                raise TypeError("language must be a string or None")
            language = self.language.strip().lower()
            if language not in {"am", "en"}:
                raise PolicyChunkError("language must be am, en, or None")
            object.__setattr__(self, "language", language)
        if self.column is not None:
            if not isinstance(self.column, str):
                raise TypeError("column must be a string or None")
            column = self.column.strip().lower()
            if column not in {"left", "right"}:
                raise PolicyChunkError("column must be left, right, or None")
            object.__setattr__(self, "column", column)
        if self.parallel_unit_id is not None:
            if not isinstance(self.parallel_unit_id, str):
                raise TypeError("parallel_unit_id must be a string or None")
            value = self.parallel_unit_id.strip()
            if not value:
                raise PolicyChunkError("parallel_unit_id must not be empty")
            object.__setattr__(self, "parallel_unit_id", value)
        if self.language is not None and self.parallel_unit_id is None:
            raise PolicyChunkError("bilingual page region requires parallel_unit_id")
        if self.language is None and self.parallel_unit_id is not None:
            raise PolicyChunkError("standard page region must not define parallel_unit_id")


class PolicyPdfExtractor:
    def __init__(self, normalizer: PolicyTextNormalizer | None = None) -> None:
        self._normalizer = normalizer or PolicyTextNormalizer()

    def extract_pages(
        self,
        pdf_path: Path | str,
        *,
        remove_repeated_marginal_lines: bool = True,
        profile: PdfExtractionProfile = PdfExtractionProfile.STANDARD,
        divider_ratio: float = 0.5,
    ) -> tuple[ExtractedPolicyPage, ...]:
        path = Path(pdf_path)
        if path.suffix.lower() != ".pdf":
            raise PolicyChunkError("policy artifact must be a PDF")
        if path.is_symlink():
            raise PolicyChunkError("symlink PDF artifacts are prohibited")
        if not path.is_file():
            raise FileNotFoundError(f"PDF source not found: {path}")
        if not isinstance(profile, PdfExtractionProfile):
            raise TypeError("profile must be a PdfExtractionProfile")
        if type(remove_repeated_marginal_lines) is not bool:
            raise TypeError("remove_repeated_marginal_lines must be a strict Boolean")
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
        if profile is PdfExtractionProfile.ETHIOPIAN_BILINGUAL_COLUMNS_V1:
            return self._extract_bilingual_pages(
                reader,
                remove_repeated_marginal_lines=remove_repeated_marginal_lines,
                divider_ratio=divider_ratio,
            )
        return self._extract_standard_pages(
            reader,
            remove_repeated_marginal_lines=remove_repeated_marginal_lines,
        )

    def _extract_standard_pages(
        self,
        reader: PdfReader,
        *,
        remove_repeated_marginal_lines: bool,
    ) -> tuple[ExtractedPolicyPage, ...]:
        raw_pages: list[str] = []
        failures: list[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw_pages.append(page.extract_text() or "")
            except Exception:
                failures.append(page_number)
                raw_pages.append("")
        self._require_no_failures(failures)
        normalized = tuple(self._normalizer.normalize_page_text(value) for value in raw_pages)
        if remove_repeated_marginal_lines:
            normalized = self._normalizer.remove_repeated_marginal_lines(normalized)
        result = tuple(
            ExtractedPolicyPage(index, text, len(text))
            for index, text in enumerate(normalized, start=1)
            if text.strip()
        )
        if not result:
            raise PolicyChunkError("standard PDF produced no extractable text")
        return result

    def _extract_bilingual_pages(
        self,
        reader: PdfReader,
        *,
        remove_repeated_marginal_lines: bool,
        divider_ratio: float,
    ) -> tuple[ExtractedPolicyPage, ...]:
        if isinstance(divider_ratio, bool) or not isinstance(divider_ratio, (int, float)):
            raise TypeError("divider_ratio must be numeric")
        divider = float(divider_ratio)
        if not 0.35 <= divider <= 0.65:
            raise PolicyChunkError("divider_ratio must be between 0.35 and 0.65")
        am_raw_pages: list[str] = []
        en_raw_pages: list[str] = []
        failures: list[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                left_text, right_text = self._extract_bilingual_page_columns(page, divider_ratio=divider)
                am_raw_pages.append(left_text)
                en_raw_pages.append(right_text)
            except Exception:
                failures.append(page_number)
                am_raw_pages.append("")
                en_raw_pages.append("")
        self._require_no_failures(failures)
        am_normalized = tuple(self._normalizer.normalize_page_text(value) for value in am_raw_pages)
        en_normalized = tuple(self._normalizer.normalize_page_text(value) for value in en_raw_pages)
        if remove_repeated_marginal_lines:
            am_normalized = self._normalizer.remove_repeated_marginal_lines(am_normalized)
            en_normalized = self._normalizer.remove_repeated_marginal_lines(en_normalized)
        result: list[ExtractedPolicyPage] = []
        for page_number, (am_text, en_text) in enumerate(zip(am_normalized, en_normalized), start=1):
            if not am_text and not en_text:
                raise PolicyChunkError(f"bilingual PDF page {page_number} produced no text in either column")
            parallel_unit_id = f"physical-page-{page_number}"
            if am_text:
                result.append(ExtractedPolicyPage(page_number, am_text, len(am_text), "am", "left", parallel_unit_id))
            if en_text:
                result.append(ExtractedPolicyPage(page_number, en_text, len(en_text), "en", "right", parallel_unit_id))
        return tuple(result)

    @staticmethod
    def _extract_bilingual_page_columns(page: Any, *, divider_ratio: float) -> tuple[str, str]:
        try:
            box = page.cropbox
            left_bound = float(box.left)
            right_bound = float(box.right)
        except Exception:
            box = page.mediabox
            left_bound = float(box.left)
            right_bound = float(box.right)
        if right_bound <= left_bound:
            raise PolicyChunkError("PDF page bounds are invalid")
        divider_x = left_bound + (right_bound - left_bound) * divider_ratio
        left_fragments: list[tuple[float, float, str, float]] = []
        right_fragments: list[tuple[float, float, str, float]] = []

        def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
            fragment = text.strip()
            if not fragment:
                return
            x, y = _matrix_position(cm, tm)
            size = float(font_size) if font_size is not None else 10.0
            target = left_fragments if x < divider_x else right_fragments
            target.append((x, y, fragment, size))

        page.extract_text(visitor_text=visitor)
        return (
            PolicyPdfExtractor._assemble_column_fragments(left_fragments),
            PolicyPdfExtractor._assemble_column_fragments(right_fragments),
        )

    @staticmethod
    def _assemble_column_fragments(
        fragments: list[tuple[float, float, str, float]],
        y_tolerance: float = 3.0,
    ) -> str:
        if isinstance(y_tolerance, bool) or not isinstance(y_tolerance, (int, float)):
            raise TypeError("y_tolerance must be numeric")
        tolerance = float(y_tolerance)
        if tolerance <= 0:
            raise PolicyChunkError("y_tolerance must be positive")
        if not fragments:
            return ""
        ordered = sorted(fragments, key=lambda value: (-value[1], value[0]))
        lines: list[list[tuple[float, float, str, float]]] = []
        line_y: list[float] = []
        for fragment in ordered:
            _, y, _, _ = fragment
            line_index = next((index for index, existing_y in enumerate(line_y) if abs(existing_y - y) <= tolerance), None)
            if line_index is None:
                line_y.append(y)
                lines.append([fragment])
            else:
                lines[line_index].append(fragment)
        rendered: list[str] = []
        for line in lines:
            line.sort(key=lambda value: value[0])
            text = ""
            previous: tuple[float, float, str, float] | None = None
            for fragment in line:
                x, _, fragment_text, font_size = fragment
                if previous is not None:
                    previous_x, _, previous_text, previous_size = previous
                    estimated_width = len(previous_text) * (previous_size * 0.45)
                    if not previous_text.endswith(" ") and not fragment_text.startswith(" ") and x - previous_x > estimated_width + previous_size * 0.15:
                        text += " "
                text += fragment_text
                previous = fragment
            cleaned = text.strip()
            if cleaned:
                rendered.append(cleaned)
        return "\n".join(rendered)

    @staticmethod
    def _require_no_failures(failures: list[int]) -> None:
        if failures:
            pages = ", ".join(str(page) for page in failures)
            raise PolicyChunkError(f"PDF text extraction failed on page(s): {pages}")
