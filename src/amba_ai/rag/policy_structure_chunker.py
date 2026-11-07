from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Protocol, Sequence

from amba_ai.governance.models import (
    ActivationStatus,
    ArtifactIntegrityStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.rag.policy_chunk_models import (
    ChunkingProfile,
    PolicyChunk,
    PolicyChunkError,
    PolicyChunkIdentity,
    require_raw_text,
)
from amba_ai.rag.policy_pdf_extractor import (
    ExtractedPolicyPage,
    PdfExtractionProfile,
    PolicyPdfExtractor,
)
from amba_ai.rag.policy_text_normalizer import PolicyTextNormalizer

_GEEZ_NUMERAL_CHARS = "፩፪፫፬፭፮፯፰፱፲፳፴፵፶፷፸፹፺፻፼"
_GEEZ_NUMERAL_PATTERN = f"[{_GEEZ_NUMERAL_CHARS}]+"

_HEADING_RE = re.compile(
    r"^(?:(?:article|section|chapter|part|clause|annex|appendix)\s+[A-Za-z0-9IVXLC.-]+|"
    r"(?:ክፍል|ንዑስ\s*ክፍል|አንቀጽ)\s+(?:" + _GEEZ_NUMERAL_PATTERN
    + r"|[A-Za-z0-9]+|አንድ|ሁለት|ሶስት|አራት|አምስት|ስድስት|ሰባት|ስምንት|ዘጠኝ|አስር)|"
    r"(?:\d+(?:\.\d+)*|" + _GEEZ_NUMERAL_PATTERN
    + r"(?:\." + _GEEZ_NUMERAL_PATTERN + r")*|[A-Z])(?:[.)])?\s+\S+|"
    r"[A-Z][A-Z0-9 /,&()\-]{4,})$",
    re.IGNORECASE,
)
_PROVISION_RE = re.compile(
    r"^(?P<id>"
    r"(?:article|section|clause|አንቀጽ)\s+[A-Za-z0-9IVXLC.፩፪፫፬፭፮፯፰፱፲፳፴፵፶፷፸፹፺፻፼-]+|"
    r"\d+(?:\.\d+)*(?:/\s*|\([a-z0-9]+\))?|"
    + _GEEZ_NUMERAL_PATTERN + r"(?:\." + _GEEZ_NUMERAL_PATTERN
    + r")*(?:/\s*|\(" + _GEEZ_NUMERAL_PATTERN + r"\))?|"
    r"\([a-z0-9" + _GEEZ_NUMERAL_CHARS + r"]+\)|"
    r"[a-zሀ-ፐ]\))\b",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?።፧፨])\s+")

_GEEZ_VALUES: dict[str, int] = {
    "፩": 1, "፪": 2, "፫": 3, "፬": 4, "፭": 5,
    "፮": 6, "፯": 7, "፰": 8, "፱": 9,
    "፲": 10, "፳": 20, "፴": 30, "፵": 40, "፶": 50,
    "፷": 60, "፸": 70, "፹": 80, "፺": 90,
    "፻": 100, "፼": 10000,
}


def geez_to_int(geez_str: str) -> int | None:
    if not isinstance(geez_str, str):
        raise TypeError("geez_str must be a string")
    cleaned = "".join(character for character in geez_str if character in _GEEZ_VALUES)
    if not cleaned:
        return None
    total = 0
    current = 0
    for character in cleaned:
        value = _GEEZ_VALUES[character]
        if value == 100:
            current = (current or 1) * 100
        elif value == 10000:
            total = (total + current or 1) * 10000
            current = 0
        else:
            current += value
    return total + current



class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class E5TokenCounter:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small") -> None:
        from transformers import AutoTokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False, truncation=False))


@dataclass(frozen=True, slots=True)
class _Unit:
    page_number: int
    section_title: str | None
    provision_numbers: tuple[str, ...]
    text: str
    language: str | None
    column: str | None
    parallel_unit_id: str | None

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not isinstance(self.page_number, int):
            raise TypeError("page_number must be an integer")
        if self.page_number < 1:
            raise PolicyChunkError("page_number must be positive")
        if not isinstance(self.text, str) or not self.text.strip():
            raise PolicyChunkError("text must be a non-empty string")
        if (self.language is None) != (self.column is None):
            raise PolicyChunkError("language and column must both be set or both be None")
        if self.language is not None and self.parallel_unit_id is None:
            raise PolicyChunkError("bilingual unit requires parallel_unit_id")
        if self.language is None and self.parallel_unit_id is not None:
            raise PolicyChunkError("standard unit must not define parallel_unit_id")


class PolicyStructureChunker:
    def __init__(
        self,
        *,
        token_counter: TokenCounter,
        profile: ChunkingProfile | None = None,
        extractor: PolicyPdfExtractor | None = None,
    ) -> None:
        if not hasattr(token_counter, "count"):
            raise TypeError("token_counter must implement count(text)")
        self._token_counter = token_counter
        self.profile = profile or ChunkingProfile()
        self._extractor = extractor or PolicyPdfExtractor()

    def chunk_pdf(
        self,
        *,
        parent_record: PolicyRecord,
        artifact_path: Path | str,
        registry: PolicyRecordRegistry,
        extraction_profile: PdfExtractionProfile = PdfExtractionProfile.STANDARD,
    ) -> tuple[PolicyChunk, ...]:
        if not isinstance(extraction_profile, PdfExtractionProfile):
            raise TypeError("extraction_profile must be a PdfExtractionProfile")
        path = Path(artifact_path)
        self._validate_record(parent_record, registry)
        self._verify_artifact(path, parent_record.artifact_sha256)
        pages = self._extractor.extract_pages(path, profile=extraction_profile)
        return self.chunk_pages(
            parent_record=parent_record,
            artifact_path=str(path),
            pages=pages,
            registry=registry,
            verify_artifact=False,
        )

    def chunk_pages(
        self,
        *,
        parent_record: PolicyRecord,
        artifact_path: Path | str,
        pages: Sequence[ExtractedPolicyPage],
        registry: PolicyRecordRegistry,
        verify_artifact: bool = True,
    ) -> tuple[PolicyChunk, ...]:
        self._validate_record(parent_record, registry)
        path = Path(artifact_path)
        if verify_artifact:
            self._verify_artifact(path, parent_record.artifact_sha256)
        selected = self._select_registered_pages(parent_record, pages)
        units = self._ordered_units(selected)
        if not units:
            raise PolicyChunkError("PolicyRecord page range produced no extractable text")
        groups = self._pack_units(units)
        chunks: list[PolicyChunk] = []
        for index, group in enumerate(groups):
            raw_text = require_raw_text(PolicyTextNormalizer.normalize_page_text("\n\n".join(unit.text for unit in group)), "raw_text")
            token_count = self._token_counter.count(raw_text)
            if token_count > self.profile.maximum_tokens:
                raise PolicyChunkError("chunk exceeds maximum_tokens")
            page_start = min(unit.page_number for unit in group)
            page_end = max(unit.page_number for unit in group)
            section_values = tuple(dict.fromkeys(unit.section_title for unit in group if unit.section_title))
            section_title = section_values[0] if len(section_values) == 1 else None
            provisions = tuple(dict.fromkeys(value for unit in group for value in unit.provision_numbers))
            locator = self._locator(parent_record.official_locator, page_start, page_end, section_title, provisions)
            text_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            languages = tuple(dict.fromkeys(unit.language for unit in group if unit.language))
            language = languages[0] if len(languages) == 1 else None
            columns = tuple(dict.fromkeys(unit.column for unit in group if unit.column))
            column = columns[0] if len(columns) == 1 else None
            parallel_ids = tuple(dict.fromkeys(unit.parallel_unit_id for unit in group if unit.parallel_unit_id))
            if language is None:
                parallel_unit_id = None
            elif page_start == page_end and len(parallel_ids) == 1:
                parallel_unit_id = f"{parent_record.identity.record_id}:{parallel_ids[0]}"
            else:
                parallel_unit_id = (
                    f"{parent_record.identity.record_id}:physical-pages-{page_start}-{page_end}"
                )
            language_part = "" if language is None else f"{language}:"
            chunk_id = (
                f"{parent_record.identity.record_id}@{parent_record.identity.version_id}:"
                f"{language_part}p{page_start}-p{page_end}:"
                f"c{index:04d}:{text_sha256[:12]}"
            )
            chunks.append(
                PolicyChunk(
                    identity=PolicyChunkIdentity(
                        chunk_id=chunk_id,
                        record_id=parent_record.identity.record_id,
                        version_id=parent_record.identity.version_id,
                        source_id=parent_record.identity.source_id,
                        chunk_index=index,
                        language=language,
                    ),
                    artifact_sha256=parent_record.artifact_sha256,
                    artifact_path=str(path),
                    page_start=page_start,
                    page_end=page_end,
                    official_locator=locator,
                    section_title=section_title,
                    provision_numbers=provisions,
                    raw_text=raw_text,
                    text_sha256=text_sha256,
                    token_count=token_count,
                    chunking_version=self.profile.version,
                    column=column,
                    parallel_unit_id=parallel_unit_id,
                )
            )
        return tuple(chunks)

    def _validate_record(self, record: PolicyRecord, registry: PolicyRecordRegistry) -> None:
        if not isinstance(record, PolicyRecord):
            raise TypeError("parent_record must be a PolicyRecord")
        if not isinstance(registry, PolicyRecordRegistry):
            raise TypeError("registry must be a PolicyRecordRegistry")
        registered = registry.require(record.identity)
        if registered != record:
            raise PolicyChunkError("parent_record conflicts with registered PolicyRecord")
        if record.activation_status is not ActivationStatus.ACTIVE:
            raise PolicyChunkError("only active PolicyRecord values may be chunked")
        if record.artifact_integrity_status is not ArtifactIntegrityStatus.VERIFIED:
            raise PolicyChunkError("artifact integrity must be verified")
        if record.metadata_verification_status is not MetadataVerificationStatus.VERIFIED:
            raise PolicyChunkError("metadata verification must be verified")
        if record.locator_verification_status not in {
            LocatorVerificationStatus.VERIFIED_EXACT,
            LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        }:
            raise PolicyChunkError("locator must be verified")
        if not registry.eligible_for_citation(record.identity):
            raise PolicyChunkError("PolicyRecord is not eligible for citation")

    @staticmethod
    def _verify_artifact(path: Path, expected_sha256: str) -> None:
        if path.suffix.lower() != ".pdf":
            raise PolicyChunkError("policy artifact must be a PDF")
        if path.is_symlink():
            raise PolicyChunkError("symlink policy artifacts are prohibited")
        if not path.is_file():
            raise FileNotFoundError(f"policy artifact not found: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise PolicyChunkError("artifact SHA-256 does not match PolicyRecord")

    @staticmethod
    def _select_registered_pages(
        record: PolicyRecord,
        pages: Sequence[ExtractedPolicyPage],
    ) -> tuple[ExtractedPolicyPage, ...]:
        if not pages:
            raise PolicyChunkError("PDF contains no extractable pages")
        keys = tuple((page.page_number, page.language, page.column) for page in pages)
        if len(keys) != len(set(keys)):
            raise PolicyChunkError("page-region identities must be unique")
        ordered = tuple(
            sorted(
                pages,
                key=lambda page: (page.page_number, page.language or "", page.column or ""),
            )
        )
        if record.page_start is None and record.page_end is None:
            return ordered
        if record.page_start is None or record.page_end is None:
            raise PolicyChunkError("PolicyRecord page range is incomplete")
        selected = tuple(
            page for page in ordered
            if record.page_start <= page.page_number <= record.page_end
        )
        actual = tuple(sorted({page.page_number for page in selected}))
        expected = tuple(range(record.page_start, record.page_end + 1))
        if actual != expected:
            raise PolicyChunkError("registered physical page range is unavailable")
        return selected

    def _ordered_units(self, pages: Sequence[ExtractedPolicyPage]) -> tuple[_Unit, ...]:
        streams: dict[tuple[str, str], list[ExtractedPolicyPage]] = {}
        for page in pages:
            key = (page.language or "", page.column or "")
            streams.setdefault(key, []).append(page)
        units: list[_Unit] = []
        for key in sorted(streams):
            for page in sorted(streams[key], key=lambda value: value.page_number):
                units.extend(self._page_units(page))
        return tuple(units)

    def _page_units(self, page: ExtractedPolicyPage) -> tuple[_Unit, ...]:
        paragraphs = tuple(value.strip() for value in page.normalized_text.split("\n\n") if value.strip())
        units: list[_Unit] = []
        section_title: str | None = None
        for paragraph in paragraphs:
            lines = tuple(line.strip() for line in paragraph.splitlines() if line.strip())
            if not lines:
                continue
            if len(lines) == 1 and len(lines[0]) <= 180 and _HEADING_RE.match(lines[0]):
                section_title = lines[0]
                continue
            provisions = tuple(
                match.group("id")
                for line in lines
                if (match := _PROVISION_RE.match(line)) is not None
            )
            unit = _Unit(
                page.page_number,
                section_title,
                tuple(dict.fromkeys(provisions)),
                paragraph,
                page.language,
                page.column,
                page.parallel_unit_id,
            )
            units.extend(self._split_oversized(unit))
        return tuple(units)

    def _split_oversized(self, unit: _Unit) -> tuple[_Unit, ...]:
        if self._token_counter.count(unit.text) <= self.profile.maximum_tokens:
            return (unit,)
        sentences = tuple(value.strip() for value in _SENTENCE_RE.split(unit.text) if value.strip())
        if len(sentences) < 2:
            windows = self._hard_windows(unit.text)
            return tuple(_Unit(unit.page_number, unit.section_title, unit.provision_numbers, value, unit.language, unit.column, unit.parallel_unit_id) for value in windows)
        output: list[_Unit] = []
        current: list[str] = []
        for sentence in sentences:
            candidate = " ".join((*current, sentence))
            if current and self._token_counter.count(candidate) > self.profile.maximum_tokens:
                output.append(_Unit(unit.page_number, unit.section_title, unit.provision_numbers, " ".join(current), unit.language, unit.column, unit.parallel_unit_id))
                current = self._sentence_overlap(current)
            current.append(sentence)
        if current:
            tail = " ".join(current)
            if self._token_counter.count(tail) <= self.profile.maximum_tokens:
                output.append(_Unit(unit.page_number, unit.section_title, unit.provision_numbers, tail, unit.language, unit.column, unit.parallel_unit_id))
            else:
                output.extend(
                    _Unit(unit.page_number, unit.section_title, unit.provision_numbers, value, unit.language, unit.column, unit.parallel_unit_id)
                    for value in self._hard_windows(tail)
                )
        return tuple(output)

    def _pack_units(self, units: Sequence[_Unit]) -> tuple[tuple[_Unit, ...], ...]:
        groups: list[tuple[_Unit, ...]] = []
        current: list[_Unit] = []
        for unit in units:
            if not current:
                current = [unit]
                continue
            candidate = "\n\n".join(value.text for value in (*current, unit))
            crosses_stream = (
                current[-1].language != unit.language
                or current[-1].column != unit.column
            )
            crosses_section = (
                current[-1].section_title is not None
                and unit.section_title is not None
                and current[-1].section_title != unit.section_title
            )
            if crosses_stream or crosses_section or self._token_counter.count(candidate) > self.profile.target_tokens:
                groups.append(tuple(current))
                current = self._unit_overlap(current, unit)
            else:
                current.append(unit)
        if current:
            if groups and self._token_counter.count("\n\n".join(value.text for value in current)) < self.profile.minimum_tokens:
                previous = groups[-1]
                same_section = previous[-1].section_title == current[0].section_title
                merged = "\n\n".join(value.text for value in (*previous, *current))
                if same_section and self._token_counter.count(merged) <= self.profile.maximum_tokens:
                    groups[-1] = (*previous, *current)
                else:
                    groups.append(tuple(current))
            else:
                groups.append(tuple(current))
        return tuple(groups)

    def _unit_overlap(self, current: Sequence[_Unit], next_unit: _Unit) -> list[_Unit]:
        if (
            self.profile.overlap_tokens == 0
            or current[-1].section_title != next_unit.section_title
            or current[-1].language != next_unit.language
            or current[-1].column != next_unit.column
        ):
            return [next_unit]
        selected: list[_Unit] = []
        total = 0
        for unit in reversed(current):
            count = self._token_counter.count(unit.text)
            if selected and total + count > self.profile.overlap_tokens:
                break
            selected.append(unit)
            total += count
            if total >= self.profile.overlap_tokens:
                break
        selected.reverse()
        return [*selected, next_unit]

    def _sentence_overlap(self, sentences: Sequence[str]) -> list[str]:
        selected: list[str] = []
        total = 0
        for sentence in reversed(sentences):
            count = self._token_counter.count(sentence)
            if selected and total + count > self.profile.overlap_tokens:
                break
            selected.append(sentence)
            total += count
            if total >= self.profile.overlap_tokens:
                break
        selected.reverse()
        return selected

    def _hard_windows(self, text: str) -> tuple[str, ...]:
        words = text.split()
        windows: list[str] = []
        start = 0
        while start < len(words):
            end = min(start + self.profile.maximum_tokens, len(words))
            candidate = " ".join(words[start:end])
            while end > start + 1 and self._token_counter.count(candidate) > self.profile.maximum_tokens:
                end -= 1
                candidate = " ".join(words[start:end])
            if self._token_counter.count(candidate) > self.profile.maximum_tokens:
                raise PolicyChunkError("tokenizer cannot produce a bounded hard window")
            windows.append(candidate)
            if end >= len(words):
                break
            overlap_start = end
            while overlap_start > start and self._token_counter.count(" ".join(words[overlap_start:end])) < self.profile.overlap_tokens:
                overlap_start -= 1
            start = max(overlap_start, start + 1)
        return tuple(windows)

    @staticmethod
    def _locator(
        official_locator: str,
        page_start: int,
        page_end: int,
        section_title: str | None,
        provision_numbers: tuple[str, ...],
    ) -> str:
        pages = f"p.{page_start}" if page_start == page_end else f"pp.{page_start}-{page_end}"
        parts = [official_locator, pages]
        if section_title:
            parts.append(section_title)
        if provision_numbers:
            parts.append("provisions " + ", ".join(provision_numbers))
        return " | ".join(parts)
