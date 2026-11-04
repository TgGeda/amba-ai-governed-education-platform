from __future__ import annotations

import html
import mimetypes
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .multimodal import (
    FigureType,
    LearningContentBundle,
    LearningFigure,
    LearningTable,
    SourceRegion,
)
from .parser import DocumentAgnosticLearningParser

# Regex patterns
_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^\"'\s)]+)(?:\s+[\"'](.*?)[\"'])?\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*?>", re.IGNORECASE)
_HTML_ALT = re.compile(r"\balt=[\"']([^\"']*)[\"']", re.IGNORECASE)
_HTML_TITLE = re.compile(r"\btitle=[\"']([^\"']*)[\"']", re.IGNORECASE)
_TABLE_ALIGN = re.compile(r"^:?-+:?$")


def _slug(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or fallback


def _source_region(metadata: Mapping[str, Any]) -> SourceRegion:
    source_name = str(
        metadata.get("original_filename")
        or metadata.get("filename")
        or metadata.get("source_name")
        or "Source unavailable"
    )
    box = tuple(metadata["bounding_box"]) if metadata.get("bounding_box") else None
    return SourceRegion(
        source_name=source_name,
        page=metadata.get("page"),
        page_end=metadata.get("page_end"),
        chunk_id=metadata.get("chunk_id"),
        bounding_box=box,
        excerpt=str(metadata.get("excerpt") or ""),
    )


def _parse_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return tuple(cell.strip() for cell in stripped.split("|"))


def _infer_column_type(values: list[str]) -> str:
    non_empty = [v for v in values if v]
    if not non_empty:
        return "text"
    if all(re.match(r"^-?\d+(?:\.\d+)?%?$", v) for v in non_empty):
        return "numeric"
    if all(re.match(r"^\d{4}-\d{2}-\d{2}$", v) for v in non_empty):
        return "date"
    return "text"


class MultimodalLearningParser:
    def __init__(self, base_parser: DocumentAgnosticLearningParser | None = None) -> None:
        self.base_parser = base_parser or DocumentAgnosticLearningParser()

    def parse(
        self,
        document_id: int,
        markdown: str,
        metadata: Mapping[str, Any] | None = None,
        assets: Sequence[Mapping[str, Any]] | None = None,
    ) -> LearningContentBundle:
        meta = dict(metadata or {})
        cleaned_text = _COMMENT.sub("", html.unescape(str(markdown or "")))
        doc = self.base_parser.parse(document_id=document_id, markdown=cleaned_text, metadata=meta)
        citation = _source_region(meta)
        tables = self._extract_tables(cleaned_text, citation)
        figures = self._extract_markdown_figures(cleaned_text, citation)
        figures.extend(self._extract_external_figures(assets or (), citation))
        unique_figures: dict[str, LearningFigure] = {f.figure_id: f for f in figures}
        return LearningContentBundle(
            document=doc,
            tables=tuple(tables),
            figures=tuple(unique_figures.values()),
            metadata={"document_id": document_id, "source": citation.source_name},
        )

    def _extract_tables(self, text: str, citation: SourceRegion) -> list[LearningTable]:
        lines = text.splitlines()
        tables: list[LearningTable] = []
        heading = "Table"
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            heading_match = re.match(r"^#{1,6}\s+(.+)$", line)
            if heading_match:
                heading = heading_match.group(1).strip()
                i += 1
                continue

            if (
                i + 1 < len(lines)
                and "|" in line
                and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1])
                and "|" in lines[i + 1]
            ):
                headers = _parse_cells(line)
                sep_cells = _parse_cells(lines[i + 1])
                alignments = []
                for s in sep_cells:
                    cleaned_s = s.strip()
                    if cleaned_s.startswith(":") and cleaned_s.endswith(":"):
                        alignments.append("center")
                    elif cleaned_s.endswith(":"):
                        alignments.append("right")
                    else:
                        alignments.append("left")

                start_idx = i
                i += 2
                row_list: list[tuple[str, ...]] = []
                while i < len(lines) and "|" in lines[i] and lines[i].strip():
                    cells = _parse_cells(lines[i])
                    if len(cells) != len(headers):
                        break
                    row_list.append(cells)
                    i += 1

                if headers and row_list:
                    raw_block = "\n".join(lines[start_idx:i])
                    col_types = []
                    for col_idx in range(len(headers)):
                        col_values = [r[col_idx] for r in row_list if col_idx < len(r)]
                        col_types.append(_infer_column_type(col_values))

                    tables.append(
                        LearningTable(
                            table_id=_slug(f"{heading}-{start_idx}", "table"),
                            title=heading,
                            headers=headers,
                            rows=tuple(row_list),
                            citations=(citation,),
                            column_alignments=tuple(alignments),
                            column_types=tuple(col_types),
                            extraction_confidence=1.0,
                            raw_source=raw_block,
                        )
                    )
                continue
            i += 1
        return tables

    def _extract_markdown_figures(self, text: str, citation: SourceRegion) -> list[LearningFigure]:
        figures: list[LearningFigure] = []
        count = 1

        for match in _MD_IMAGE.finditer(text):
            alt_text, path, title = match.groups()
            media_type = mimetypes.guess_type(path)[0] or "image/png"
            fig_type = FigureType.IMAGE
            path_lower = path.lower()
            if any(term in path_lower for term in ("diagram", "flowchart", "architecture")):
                fig_type = FigureType.DIAGRAM
            elif any(term in path_lower for term in ("chart", "graph", "plot")):
                fig_type = FigureType.CHART
            elif "formula" in path_lower or "equation" in path_lower:
                fig_type = FigureType.EQUATION

            figures.append(
                LearningFigure(
                    figure_id=_slug(f"fig-{count}-{Path(path).stem}", "figure"),
                    asset_path=path,
                    media_type=media_type,
                    caption=title or "",
                    alt_text=alt_text or "",
                    educational_summary=alt_text or title or "",
                    figure_type=fig_type,
                    citations=(citation,),
                )
            )
            count += 1

        for match in _HTML_IMAGE.finditer(text):
            tag = match.group(0)
            src = match.group(1)
            alt_match = _HTML_ALT.search(tag)
            title_match = _HTML_TITLE.search(tag)
            alt_text = alt_match.group(1) if alt_match else ""
            title = title_match.group(1) if title_match else ""
            media_type = mimetypes.guess_type(src)[0] or "image/png"

            figures.append(
                LearningFigure(
                    figure_id=_slug(f"fig-{count}-{Path(src).stem}", "figure"),
                    asset_path=src,
                    media_type=media_type,
                    caption=title,
                    alt_text=alt_text,
                    educational_summary=alt_text or title,
                    figure_type=FigureType.IMAGE,
                    citations=(citation,),
                )
            )
            count += 1

        return figures

    def _extract_external_figures(
        self,
        assets: Sequence[Mapping[str, Any]],
        default_citation: SourceRegion,
    ) -> list[LearningFigure]:
        figures: list[LearningFigure] = []
        for index, asset in enumerate(assets, 1):
            path = str(asset.get("asset_path") or asset.get("path") or "").strip()
            if not path:
                continue
            box = tuple(asset["bounding_box"]) if asset.get("bounding_box") else None
            region = SourceRegion(
                source_name=str(asset.get("source_name") or default_citation.source_name),
                page=asset.get("page") or default_citation.page,
                page_end=asset.get("page_end") or default_citation.page_end,
                chunk_id=asset.get("chunk_id"),
                bounding_box=box,
                excerpt=str(asset.get("excerpt") or ""),
            )
            raw_type = str(asset.get("figure_type") or "image").lower()
            try:
                fig_type = FigureType(raw_type)
            except ValueError:
                fig_type = FigureType.IMAGE

            figures.append(
                LearningFigure(
                    figure_id=str(asset.get("figure_id") or _slug(f"asset-{index}-{Path(path).stem}", "figure")),
                    asset_path=path,
                    media_type=str(asset.get("media_type") or mimetypes.guess_type(path)[0] or "image/png"),
                    caption=str(asset.get("caption") or ""),
                    alt_text=str(asset.get("alt_text") or ""),
                    educational_summary=str(asset.get("educational_summary") or ""),
                    figure_type=fig_type,
                    citations=(region,),
                    width=asset.get("width"),
                    height=asset.get("height"),
                    checksum=str(asset.get("checksum") or ""),
                    ocr_text=str(asset.get("ocr_text") or ""),
                    embedded_labels=tuple(asset.get("embedded_labels") or ()),
                    visual_complexity=str(asset.get("visual_complexity") or "medium"),
                )
            )
        return figures