from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

MULTIMODAL_SCHEMA_VERSION = "ambaai.learning-content.multimodal.v2"


class FigureType(str, Enum):
    IMAGE = "image"
    DIAGRAM = "diagram"
    CHART = "chart"
    GRAPH = "graph"
    FLOWCHART = "flowchart"
    SCREENSHOT = "screenshot"
    ILLUSTRATION = "illustration"
    MAP = "map"
    TIMELINE = "timeline"
    EQUATION = "equation"
    SCANNED_REGION = "scanned_page_region"
    INFOGRAPHIC = "infographic"
    SCHEMATIC = "schematic"


@dataclass(frozen=True, slots=True)
class SourceRegion:
    source_name: str
    page: int | None = None
    page_end: int | None = None
    chunk_id: str | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    excerpt: str = ""

    @property
    def label(self) -> str:
        if self.page is None:
            return self.source_name
        if self.page_end and self.page_end != self.page:
            return f"{self.source_name} · Pages {self.page}–{self.page_end}"
        return f"{self.source_name} · Page {self.page}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningTable:
    table_id: str
    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    caption: str = ""
    summary: str = ""
    citations: tuple[SourceRegion, ...] = ()
    column_alignments: tuple[str, ...] = ()
    column_types: tuple[str, ...] = ()
    has_header_row: bool = True
    extraction_confidence: float | None = None
    raw_source: str = ""

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return len(self.headers) if self.headers else (len(self.rows[0]) if self.rows else 0)

    def to_markdown(self) -> str:
        if not self.headers and not self.rows:
            return ""
        lines: list[str] = []
        if self.headers:
            lines.append("| " + " | ".join(self.headers) + " |")
            lines.append("| " + " | ".join("---" for _ in self.headers) + " |")
        for row in self.rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningFigure:
    figure_id: str
    asset_path: str
    media_type: str
    caption: str = ""
    alt_text: str = ""
    educational_summary: str = ""
    figure_type: FigureType = FigureType.IMAGE
    citations: tuple[SourceRegion, ...] = ()
    width: int | None = None
    height: int | None = None
    checksum: str = ""
    ocr_text: str = ""
    embedded_labels: tuple[str, ...] = ()
    visual_complexity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["figure_type"] = self.figure_type.value
        return d


@dataclass(frozen=True, slots=True)
class LearningContentBundle:
    document: Any
    tables: tuple[LearningTable, ...] = ()
    figures: tuple[LearningFigure, ...] = ()
    schema_version: str = MULTIMODAL_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def get_figure(self, figure_id: str) -> LearningFigure | None:
        for figure in self.figures:
            if figure.figure_id == figure_id:
                return figure
        return None

    def get_table(self, table_id: str) -> LearningTable | None:
        for table in self.tables:
            if table.table_id == table_id:
                return table
        return None

    def to_dict(self) -> dict[str, Any]:
        def convert(val: Any) -> Any:
            if isinstance(val, Enum):
                return val.value
            if hasattr(val, "to_dict"):
                return val.to_dict()
            if isinstance(val, (tuple, list)):
                return [convert(item) for item in val]
            if isinstance(val, dict):
                return {str(k): convert(v) for k, v in val.items()}
            return val

        return {
            "document": convert(self.document),
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
        }