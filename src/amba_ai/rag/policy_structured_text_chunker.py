from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from amba_ai.governance.models import to_canonical_json


_HEADING_PATTERN = re.compile(
    r"^(?P<kind>article|subarticle|clause|section|definition|exception|"
    r"requirement|objective|dimension|metric|table row)"
    r"(?:\s+(?P<label>[^\n:]+?))?\s*:?[ \t]*$",
    re.IGNORECASE,
)
_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<label>(?:\d+(?:\.\d+)*|[A-Z]|[ivxlcdm]+)[.)]?)\s+\S.*$",
    re.IGNORECASE,
)
_TABLE_SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(field_name, str):
        raise TypeError(
            "field_name must be a string"
        )

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError(
            "field_name must not be empty"
        )

    if not isinstance(value, str):
        raise TypeError(
            f"{normalized_field_name} must be a string"
        )

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(
            f"{normalized_field_name} must not be empty"
        )

    return normalized_value


def _normalize_line(line: str) -> str:
    return _WHITESPACE_PATTERN.sub(
        " ",
        line.strip(),
    )


def _normalize_text(text: str) -> str:
    normalized_newlines = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    lines = [
        _normalize_line(line)
        for line in normalized_newlines.split("\n")
    ]

    normalized: list[str] = []
    previous_blank = False

    for line in lines:
        blank = not line

        if blank and previous_blank:
            continue

        normalized.append(line)
        previous_blank = blank

    return "\n".join(normalized).strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class StructuredPolicyTextChunk:
    chunk_id: str
    record_id: str
    sequence: int
    structure_type: str
    section_path: str
    text: str
    locator: str
    text_sha256: str

    def __post_init__(self) -> None:
        chunk_id = _require_text(
            self.chunk_id,
            "chunk_id",
        )
        record_id = _require_text(
            self.record_id,
            "record_id",
        )
        structure_type = _require_text(
            self.structure_type,
            "structure_type",
        )
        section_path = _require_text(
            self.section_path,
            "section_path",
        )
        text = _require_text(
            self.text,
            "text",
        )
        locator = _require_text(
            self.locator,
            "locator",
        )

        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
        ):
            raise TypeError(
                "sequence must be an integer"
            )

        if self.sequence < 1:
            raise ValueError(
                "sequence must be strictly positive"
            )

        if (
            not isinstance(self.text_sha256, str)
            or re.fullmatch(
                r"[0-9a-f]{64}",
                self.text_sha256,
            )
            is None
        ):
            raise ValueError(
                "text_sha256 must be exactly 64 "
                "lowercase hexadecimal characters"
            )

        if _sha256_text(text) != self.text_sha256:
            raise ValueError(
                "text_sha256 does not match text"
            )

        object.__setattr__(
            self,
            "chunk_id",
            chunk_id,
        )
        object.__setattr__(
            self,
            "record_id",
            record_id,
        )
        object.__setattr__(
            self,
            "structure_type",
            structure_type,
        )
        object.__setattr__(
            self,
            "section_path",
            section_path,
        )
        object.__setattr__(
            self,
            "text",
            text,
        )
        object.__setattr__(
            self,
            "locator",
            locator,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "record_id": self.record_id,
            "sequence": self.sequence,
            "structure_type": self.structure_type,
            "section_path": self.section_path,
            "text": self.text,
            "locator": self.locator,
            "text_sha256": self.text_sha256,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


@dataclass(frozen=True, slots=True)
class _Unit:
    structure_type: str
    section_path: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "structure_type",
            _require_text(
                self.structure_type,
                "structure_type",
            ),
        )
        object.__setattr__(
            self,
            "section_path",
            _require_text(
                self.section_path,
                "section_path",
            ),
        )
        object.__setattr__(
            self,
            "text",
            _require_text(
                self.text,
                "text",
            ),
        )


class StructuredPolicyTextChunker:
    def chunk(
        self,
        *,
        record_id: str,
        text: str,
        locator: str,
    ) -> tuple[StructuredPolicyTextChunk, ...]:
        record = _require_text(
            record_id,
            "record_id",
        )
        material = _normalize_text(
            _require_text(
                text,
                "text",
            )
        )
        source_locator = _require_text(
            locator,
            "locator",
        )

        units = self._extract_units(
            material
        )
        chunks: list[StructuredPolicyTextChunk] = []

        for sequence, unit in enumerate(
            units,
            start=1,
        ):
            chunk_material = {
                "record_id": record,
                "sequence": sequence,
                "structure_type": (
                    unit.structure_type
                ),
                "section_path": (
                    unit.section_path
                ),
                "text": unit.text,
                "locator": source_locator,
            }

            encoded_material = (
                to_canonical_json(
                    chunk_material
                )
            )
            chunk_digest = _sha256_text(
                encoded_material
            )
            chunk_id = (
                f"{record}:policy-chunk:"
                f"{chunk_digest[:16]}"
            )

            chunks.append(
                StructuredPolicyTextChunk(
                    chunk_id=chunk_id,
                    record_id=record,
                    sequence=sequence,
                    structure_type=(
                        unit.structure_type
                    ),
                    section_path=(
                        unit.section_path
                    ),
                    text=unit.text,
                    locator=source_locator,
                    text_sha256=_sha256_text(
                        unit.text
                    ),
                )
            )

        return tuple(chunks)

    def _extract_units(
        self,
        material: str,
    ) -> tuple[_Unit, ...]:
        lines = material.splitlines()
        units: list[_Unit] = []
        active_lines: list[str] = []
        active_type = "policy_text"
        active_path = "Policy text"
        section_stack: list[str] = []
        table_header: str | None = None

        def flush() -> None:
            nonlocal active_lines

            unit_text = "\n".join(
                active_lines
            ).strip()

            if unit_text:
                units.append(
                    _Unit(
                        structure_type=active_type,
                        section_path=active_path,
                        text=unit_text,
                    )
                )

            active_lines = []

        index = 0

        while index < len(lines):
            stripped = lines[index].strip()

            if not stripped:
                if (
                    active_lines
                    and active_lines[-1] != ""
                ):
                    active_lines.append("")

                index += 1
                continue

            if self._is_table_header(
                lines,
                index,
            ):
                flush()

                table_header = stripped

                index += 2
                continue

            if (
                table_header is not None
                and self._is_table_row(
                    stripped
                )
            ):
                units.append(
                    _Unit(
                        structure_type="table_row",
                        section_path=" > ".join(
                            section_stack
                            or ["Table"]
                        ),
                        text=(
                            f"{table_header}\n"
                            f"{stripped}"
                        ),
                    )
                )

                index += 1
                continue

            if table_header is not None:
                table_header = None

            heading = self._heading(
                stripped
            )

            if heading is not None:
                flush()

                active_type, heading_text = heading

                section_stack = (
                    self._update_section_stack(
                        section_stack,
                        active_type,
                        heading_text,
                    )
                )

                active_path = " > ".join(
                    section_stack
                )

                active_lines = [stripped]

                index += 1
                continue

            active_lines.append(stripped)

            index += 1

        flush()

        if not units:
            units.append(
                _Unit(
                    structure_type="policy_text",
                    section_path="Policy text",
                    text=material,
                )
            )

        return tuple(units)

    @staticmethod
    def _is_table_separator(
        line: str,
    ) -> bool:
        normalized = line.strip()

        if not normalized:
            return False

        if normalized.startswith("|"):
            normalized = normalized[1:]

        if normalized.endswith("|"):
            normalized = normalized[:-1]

        cells = tuple(
            cell.strip()
            for cell in normalized.split("|")
        )

        if len(cells) < 2:
            return False

        return all(
            _TABLE_SEPARATOR_CELL_PATTERN.fullmatch(
                cell
            )
            is not None
            for cell in cells
        )


    @classmethod
    def _is_table_header(
        cls,
        lines: list[str],
        index: int,
    ) -> bool:
        if index + 1 >= len(lines):
            return False

        header = lines[index].strip()
        separator = lines[
            index + 1
        ].strip()

        return (
            cls._is_table_row(header)
            and cls._is_table_separator(
                separator
            )
        )


    @staticmethod
    def _heading(
        line: str,
    ) -> tuple[str, str] | None:
        if StructuredPolicyTextChunker._is_table_row(
            line
        ):
            return None

        explicit = _HEADING_PATTERN.fullmatch(
            line
        )

        if explicit is not None:
            kind = (
                explicit.group("kind")
                .casefold()
                .replace(" ", "_")
            )
            return kind, line[:240]

        if _NUMBERED_HEADING_PATTERN.fullmatch(
            line
        ):
            return (
                "numbered_paragraph",
                line[:240],
            )

        return None


    @staticmethod
    def _is_table_row(
        line: str,
    ) -> bool:
        normalized = line.strip()

        if normalized.startswith("|"):
            normalized = normalized[1:]

        if normalized.endswith("|"):
            normalized = normalized[:-1]

        cells = tuple(
            cell.strip()
            for cell in normalized.split("|")
        )

        return (
            len(cells) >= 2
            and all(cells)
        )
    @staticmethod
    def _update_section_stack(
        current: list[str],
        structure_type: str,
        heading_text: str,
    ) -> list:
        top_level = {
            "article",
            "section",
            "dimension",
            "objective",
        }
        nested = {
            "subarticle",
            "clause",
            "definition",
            "exception",
            "requirement",
            "metric",
            "numbered_paragraph",
        }

        if structure_type in top_level:
            return [heading_text]

        if structure_type in nested:
            if current:
                return [
                    *current[:1],
                    heading_text,
                ]

            return [heading_text]

        return [heading_text]
