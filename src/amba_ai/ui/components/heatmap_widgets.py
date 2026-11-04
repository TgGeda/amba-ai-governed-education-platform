from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from amba_ai.logger import logger

try:
    from PySide6.QtCharts import (
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QChart,
        QChartView,
        QValueAxis,
    )
except Exception:
    QBarCategoryAxis = None
    QBarSeries = None
    QBarSet = None
    QChart = None
    QChartView = None
    QValueAxis = None


@dataclass(frozen=True)
class UsageHeatmapItem:
    """
    Normalized document usage item for rendering.
    """

    document_id: int | None
    title: str
    usage_count: int


class UsageHeatmapWidget(QWidget):
    """
    Lightweight library usage heatmap widget.

    Displays the top-used documents as a bar chart when QtCharts is available.
    Falls back to a text summary when QtCharts is unavailable.
    """

    MAX_ITEMS = 10
    EMPTY_TEXT = "No usage data available."
    CHART_TITLE = "Most Used Documents"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._items: list[UsageHeatmapItem] = []
        self._current_widget: QWidget | None = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)

        self._show_empty_state()

    def update(self, docs: Iterable[Any] | None = None) -> None:  # type: ignore[override]
        """
        Compatibility wrapper.

        If docs is provided, update heatmap data.
        If docs is None, preserve QWidget.update() behavior.
        """
        if docs is None:
            super().update()
            return

        self.update_heatmap(docs)

    def update_heatmap(self, docs: Iterable[Any]) -> None:
        """
        Update chart using document objects or dictionaries.

        Supported fields:
        - document_id / id
        - title
        - usage_count
        """
        self._items = self._normalize_documents(docs)

        if not self._items:
            self._show_empty_state()
            return

        if not self._qtcharts_available():
            self._show_text_fallback()
            return

        try:
            chart = self._build_chart(self._items)
            chart_view = QChartView(chart)
            chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._replace_widget(chart_view)

            logger.info(
                "Usage heatmap updated",
                extra={"context": {"item_count": len(self._items)}},
            )

        except Exception:
            logger.exception("Failed to render usage heatmap")
            self._show_text_fallback()

    def clear(self) -> None:
        """
        Clear chart data and show empty state.
        """
        self._items.clear()
        self._show_empty_state()

    def _build_chart(self, items: list[UsageHeatmapItem]) -> Any:
        if not self._qtcharts_available():
            raise RuntimeError("QtCharts is unavailable.")

        bar_set = QBarSet("Usage")
        labels: list[str] = []
        max_usage = 0

        for item in items:
            usage = max(0, int(item.usage_count))
            bar_set.append(usage)
            labels.append(self._short_title(item.title))
            max_usage = max(max_usage, usage)

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(self.CHART_TITLE)
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max(1, max_usage))
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        return chart

    def _show_empty_state(self) -> None:
        label = QLabel(self.EMPTY_TEXT)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray;")
        self._replace_widget(label)

    def _show_text_fallback(self) -> None:
        if not self._items:
            self._show_empty_state()
            return

        lines = ["Most used documents:"]
        for index, item in enumerate(self._items, start=1):
            lines.append(f"{index}. {item.title} — {item.usage_count}")

        label = QLabel("\n".join(lines))
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setStyleSheet("color: gray; padding: 6px;")
        self._replace_widget(label)

    def _replace_widget(self, widget: QWidget) -> None:
        if self._current_widget is not None:
            self.layout.removeWidget(self._current_widget)
            self._current_widget.deleteLater()
            self._current_widget = None

        self._current_widget = widget
        self.layout.addWidget(widget)

    @classmethod
    def _normalize_documents(cls, docs: Iterable[Any]) -> list[UsageHeatmapItem]:
        items: list[UsageHeatmapItem] = []

        for doc in docs:
            try:
                item = cls._normalize_document(doc)
            except Exception:
                logger.warning(
                    "Invalid heatmap document skipped",
                    extra={"context": {"document": str(doc)[:300]}},
                    exc_info=True,
                )
                continue

            if item.usage_count > 0:
                items.append(item)

        items.sort(key=lambda item: item.usage_count, reverse=True)
        return items[: cls.MAX_ITEMS]

    @staticmethod
    def _normalize_document(doc: Any) -> UsageHeatmapItem:
        if isinstance(doc, dict):
            document_id = doc.get("document_id", doc.get("id"))
            title = str(doc.get("title") or "Untitled")
            usage_count = int(doc.get("usage_count") or 0)
        else:
            document_id = getattr(doc, "document_id", getattr(doc, "id", None))
            title = str(getattr(doc, "title", "Untitled"))
            usage_count = int(getattr(doc, "usage_count", 0) or 0)

        return UsageHeatmapItem(
            document_id=int(document_id) if document_id is not None else None,
            title=title,
            usage_count=usage_count,
        )

    @staticmethod
    def _short_title(title: str, max_length: int = 14) -> str:
        clean = " ".join((title or "Untitled").split())

        if len(clean) <= max_length:
            return clean

        return clean[: max_length - 1] + "…"

    @staticmethod
    def _qtcharts_available() -> bool:
        return all(
            item is not None
            for item in (
                QBarCategoryAxis,
                QBarSeries,
                QBarSet,
                QChart,
                QChartView,
                QValueAxis,
            )
        )