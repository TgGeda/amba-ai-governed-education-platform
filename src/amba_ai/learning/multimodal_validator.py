from __future__ import annotations

from dataclasses import dataclass
from .multimodal import LearningContentBundle


@dataclass(frozen=True, slots=True)
class MultimodalIssue:
    severity: str
    code: str
    message: str
    object_id: str = ""


@dataclass(frozen=True, slots=True)
class MultimodalValidationReport:
    valid: bool
    issues: tuple[MultimodalIssue, ...]
    quality_score: float = 1.0


class MultimodalLearningValidator:
    def validate(self, bundle: LearningContentBundle) -> MultimodalValidationReport:
        issues: list[MultimodalIssue] = []
        seen_table_ids: set[str] = set()

        for table in bundle.tables:
            if table.table_id in seen_table_ids:
                issues.append(
                    MultimodalIssue(
                        "error",
                        "duplicate_table_id",
                        f"Duplicate table ID: {table.table_id}",
                        table.table_id,
                    )
                )
            seen_table_ids.add(table.table_id)

            if not table.headers and not table.rows:
                issues.append(
                    MultimodalIssue(
                        "error",
                        "empty_table",
                        f"Table has no headers or rows: {table.title}",
                        table.table_id,
                    )
                )
                continue

            expected_width = (
                len(table.headers)
                if table.headers
                else (len(table.rows[0]) if table.rows else 0)
            )
            if expected_width == 0:
                issues.append(
                    MultimodalIssue(
                        "error",
                        "zero_column_table",
                        f"Table has zero columns: {table.title}",
                        table.table_id,
                    )
                )
                continue

            for row_idx, row in enumerate(table.rows):
                if len(row) != expected_width:
                    issues.append(
                        MultimodalIssue(
                            "error",
                            "ragged_table_row",
                            f"Row {row_idx} width ({len(row)}) differs from header width ({expected_width}) in {table.title}",
                            table.table_id,
                        )
                    )

        seen_fig_ids: set[str] = set()
        for figure in bundle.figures:
            if figure.figure_id in seen_fig_ids:
                issues.append(
                    MultimodalIssue(
                        "error",
                        "duplicate_figure_id",
                        f"Duplicate figure ID: {figure.figure_id}",
                        figure.figure_id,
                    )
                )
            seen_fig_ids.add(figure.figure_id)

            if not figure.asset_path.strip():
                issues.append(
                    MultimodalIssue(
                        "error",
                        "missing_asset_path",
                        "Figure lacks an asset path",
                        figure.figure_id,
                    )
                )

            if not figure.alt_text.strip():
                issues.append(
                    MultimodalIssue(
                        "warning",
                        "missing_alt_text",
                        "Figure has no accessibility alt text",
                        figure.figure_id,
                    )
                )

            if not figure.citations:
                issues.append(
                    MultimodalIssue(
                        "warning",
                        "missing_figure_citation",
                        "Figure lacks citation region",
                        figure.figure_id,
                    )
                )

            for cit in figure.citations:
                if cit.bounding_box:
                    x0, y0, x1, y1 = cit.bounding_box
                    if x0 < 0.0 or y0 < 0.0 or x1 > 1.0 or y1 > 1.0 or x0 >= x1 or y0 >= y1:
                        issues.append(
                            MultimodalIssue(
                                "error",
                                "invalid_bounding_box",
                                f"Invalid bounding box {cit.bounding_box}",
                                figure.figure_id,
                            )
                        )

        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        quality = max(0.0, min(1.0, 1.0 - (error_count * 0.25) - (warning_count * 0.05)))

        return MultimodalValidationReport(
            valid=error_count == 0,
            issues=tuple(issues),
            quality_score=round(quality, 2),
        )