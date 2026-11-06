from __future__ import annotations

from collections import Counter
import re
from typing import Sequence

_CONSECUTIVE_NEWLINES = re.compile(r"\n{3,}")
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")


class PolicyTextNormalizer:
    @staticmethod
    def normalize_page_text(raw_text: str) -> str:
        if not isinstance(raw_text, str):
            raise TypeError("raw_text must be a string")
        if not raw_text:
            return ""
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = _HORIZONTAL_WHITESPACE.sub(" ", text)
        lines = tuple(line.strip() for line in text.split("\n"))
        text = "\n".join(lines)
        text = _CONSECUTIVE_NEWLINES.sub("\n\n", text)
        return text.strip()

    @staticmethod
    def remove_repeated_marginal_lines(
        pages: Sequence[str],
        *,
        minimum_pages: int = 3,
        maximum_line_length: int = 160,
    ) -> tuple[str, ...]:
        if isinstance(minimum_pages, bool) or not isinstance(minimum_pages, int):
            raise TypeError("minimum_pages must be an integer")
        if minimum_pages < 2:
            raise ValueError("minimum_pages must be at least 2")
        if isinstance(maximum_line_length, bool) or not isinstance(maximum_line_length, int):
            raise TypeError("maximum_line_length must be an integer")
        if maximum_line_length < 1:
            raise ValueError("maximum_line_length must be positive")
        normalized = tuple(PolicyTextNormalizer.normalize_page_text(page) for page in pages)
        candidates: Counter[str] = Counter()
        for page in normalized:
            lines = tuple(line for line in page.splitlines() if line)
            marginal = set(lines[:2] + lines[-2:])
            for line in marginal:
                if len(line) <= maximum_line_length:
                    candidates[line] += 1
        repeated = {line for line, count in candidates.items() if count >= minimum_pages}
        if not repeated:
            return normalized
        cleaned: list[str] = []
        for page in normalized:
            lines = page.splitlines()
            kept = [line for line in lines if line not in repeated]
            cleaned.append(PolicyTextNormalizer.normalize_page_text("\n".join(kept)))
        return tuple(cleaned)
